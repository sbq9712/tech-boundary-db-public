#!/usr/bin/env python3
"""
批量读取 PDF，提取“产业技术情报”/“技术追踪”下与“碳捕集利用”相关的二级标题内容，
并转换为系统可批量上传的 CSV 格式。

默认行为：
1. 仅保留二级标题中包含“碳捕集利用”的章节
2. “产业技术情报” -> source_types = 产业新闻
3. “技术追踪” -> source_types = 学术文献
4. info_types 固定为 技术
5. is_new_tech 固定为 false
6. classification 固定为 内部
7. alert_manual 固定为 false
8. domains 根据标题和正文关键词映射到 CCUS 细分领域
9. importance_score / tags 优先由 AI 判断，无 AI 时退化为规则判断
10. 指标字段根据正文提取并映射到预设指标名

依赖：
- pypdf

示例：
python3 scripts/pdf_to_ccus_upload_csv.py \
  --input-dir /path/to/pdfs \
  --output /path/to/output.csv

可选 AI：
export OPENAI_API_KEY=xxx
python3 scripts/pdf_to_ccus_upload_csv.py --input-dir ./pdfs --output ./ccus_upload.csv --use-ai
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import error, request

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "缺少依赖 pypdf，请先执行: python3 -m pip install pypdf"
    ) from exc


CSV_HEADERS = [
    "title",
    "published_at",
    "source_url",
    "source_types",
    "info_types",
    "domains",
    "importance_score",
    "is_new_tech",
    "content",
    "tags",
    "classification",
    "comment",
    "alert_manual",
    "alert_title",
    "alert_body",
    "reviewer_comment",
    "duration",
    "custom_expires_on",
    "alert_color",
]
for i in range(1, 21):
    CSV_HEADERS.extend(
        [f"indicator_{i}_name", f"indicator_{i}_value", f"indicator_{i}_unit"]
    )


TOP_TITLE_TO_SOURCE_TYPE = {
    "产业技术情报": "产业新闻",
    "技术追踪": "学术文献",
}


DOMAIN_KEYWORDS = {
    "DOM_CCUS_L2_CAPTURE": [
        "捕集",
        "吸收",
        "吸附",
        "膜分离",
        "相变分离",
        "化学链",
        "电化学分离",
        "直接空气捕集",
        "DAC",
    ],
    "DOM_CCUS_L2_TRANSPORT": [
        "运输",
        "管道",
        "槽车",
        "船运",
        "储运",
        "压缩",
        "液化",
        "运输距离",
    ],
    "DOM_CCUS_L2_UTILIZATION": [
        "利用",
        "资源化",
        "矿化",
        "合成甲醇",
        "电催化还原",
        "尿素",
        "混凝土",
        "驱油",
        "转化",
    ],
    "DOM_CCUS_L2_STORAGE": [
        "封存",
        "储存",
        "咸水层",
        "油藏",
        "气藏",
        "地质封存",
        "注入",
        "井筒",
    ],
    "DOM_CCUS_L2_SUPPORT": [
        "监测",
        "传感",
        "压缩机",
        "泵",
        "换热",
        "模拟",
        "仿真",
        "控制系统",
    ],
}


SECONDARY_HEADING_PATTERNS = [
    re.compile(r"^\s*([一二三四五六七八九十]+)[、.．]\s*(.+)$"),
    re.compile(r"^\s*([0-9]{1,2})[、.．]\s*(.+)$"),
    re.compile(r"^\s*[(（]([一二三四五六七八九十0-9]{1,3})[)）]\s*(.+)$"),
]


COMMENT_SPLIT_PATTERNS = [
    re.compile(r"(?:^|\n)\s*(评论|点评|评述|简评)\s*[:：]?\s*", re.MULTILINE),
]


DATE_PATTERNS = [
    re.compile(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
]


UNIT_PATTERN = (
    r"GJ/tCO[₂2]|kWh/tCO[₂2]|gCO[₂2]/g·h|gCO[₂2]/g|Mt/年|万吨/年|元/kg|元/t"
    r"|元/tCO2|元/tCO[₂2]|元/km|元/t·km|km|MPa|℃|%/年|%|m|t/天|年|圈|kW|RMB"
)


@dataclass
class IndicatorDef:
    name: str
    match_name: str
    unit_default: str
    data_type: str
    allowed_domain_ids: List[str]


@dataclass
class SectionRecord:
    title: str
    top_title: str
    source_type: str
    content: str
    comment: str
    published_at: str
    pdf_name: str
    domains: List[str] = field(default_factory=list)
    importance_score: int = 3
    tags: List[str] = field(default_factory=list)
    indicators: List[Tuple[str, str, str]] = field(default_factory=list)


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = text.replace("\xa0", " ")
    text = text.replace("CO₂", "CO2")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return normalize_text("\n".join(pages))


def find_first_date(text: str, fallback_name: str) -> str:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    for pattern in DATE_PATTERNS:
        match = pattern.search(fallback_name)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return ""


def split_by_top_titles(text: str) -> List[Tuple[str, str]]:
    titles = list(TOP_TITLE_TO_SOURCE_TYPE.keys())
    positions: List[Tuple[int, str]] = []
    for title in titles:
        for match in re.finditer(re.escape(title), text):
            positions.append((match.start(), title))
            break
    positions.sort(key=lambda item: item[0])
    if not positions:
        return []

    chunks: List[Tuple[str, str]] = []
    for idx, (start_pos, title) in enumerate(positions):
        end_pos = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        chunk = text[start_pos:end_pos].strip()
        chunks.append((title, chunk))
    return chunks


def locate_secondary_headings(lines: Sequence[str]) -> List[Tuple[int, str]]:
    found: List[Tuple[int, str]] = []
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        for pattern in SECONDARY_HEADING_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            title_text = match.group(2).strip()
            found.append((idx, title_text))
            break
    return found


def split_comment(content: str) -> Tuple[str, str]:
    for pattern in COMMENT_SPLIT_PATTERNS:
        match = pattern.search(content)
        if match:
            body = content[: match.start()].strip()
            comment = content[match.end() :].strip()
            return body, comment
    return content.strip(), ""


def extract_sections(text: str, pdf_name: str) -> List[SectionRecord]:
    published_at = find_first_date(text, pdf_name)
    top_chunks = split_by_top_titles(text)
    if not top_chunks:
        return []

    sections: List[SectionRecord] = []
    for top_title, chunk in top_chunks:
        source_type = TOP_TITLE_TO_SOURCE_TYPE[top_title]
        lines = [line.strip() for line in chunk.splitlines()]
        headings = locate_secondary_headings(lines)
        if not headings:
            continue

        for idx, (line_no, sec_title) in enumerate(headings):
            if "碳捕集利用" not in sec_title:
                continue
            start = line_no + 1
            end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
            section_text = "\n".join(line for line in lines[start:end] if line).strip()
            if not section_text:
                continue
            body, comment = split_comment(section_text)
            sections.append(
                SectionRecord(
                    title=sec_title,
                    top_title=top_title,
                    source_type=source_type,
                    content=body,
                    comment=comment,
                    published_at=published_at,
                    pdf_name=pdf_name,
                )
            )
    return sections


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_indicator_defs(path: Path) -> List[IndicatorDef]:
    raw = load_json(path)
    defs: List[IndicatorDef] = []
    for item in raw:
        if not item.get("is_active", False):
            continue
        defs.append(
            IndicatorDef(
                name=item["name"],
                match_name=item["match_name"],
                unit_default=item.get("unit_default", ""),
                data_type=item["data_type"],
                allowed_domain_ids=item.get("allowed_domain_ids", []),
            )
        )
    return defs


def load_domain_lookup(path: Path) -> Dict[str, Dict[str, str]]:
    raw = load_json(path)
    return {item["id"]: item for item in raw if item.get("is_active", False)}


def infer_domains(title: str, content: str, domain_lookup: Dict[str, Dict[str, str]]) -> List[str]:
    text = f"{title}\n{content}"
    scores: Dict[str, int] = {}

    for domain_id, keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for kw in keywords:
            score += text.count(kw)
        if score > 0 and domain_id in domain_lookup:
            scores[domain_id] = score

    if not scores:
        return ["DOM_CCUS_L1"]

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    winners = [domain_id for domain_id, _ in ranked[:2]]
    return winners


def normalize_unit(unit: str) -> str:
    return (
        unit.replace("CO₂", "CO2")
        .replace("（", "(")
        .replace("）", ")")
        .replace("·", "·")
        .strip()
    )


def unit_variants(unit: str) -> List[str]:
    if not unit:
        return []
    variants = {normalize_unit(unit)}
    replacements = {
        "CO2": ["CO₂"],
        "(": ["（"],
        ")": ["）"],
    }
    seed = list(variants)
    for item in seed:
        for src, targets in replacements.items():
            if src in item:
                for dst in targets:
                    variants.add(item.replace(src, dst))
    return sorted(variants, key=len, reverse=True)


def build_indicator_patterns(indicator: IndicatorDef) -> List[re.Pattern[str]]:
    escaped_name = re.escape(indicator.match_name)
    patterns: List[re.Pattern[str]] = []

    if indicator.data_type == "number":
        units = unit_variants(indicator.unit_default)
        unit_part = "|".join(re.escape(unit) for unit in units) if units else UNIT_PATTERN
        patterns.append(
            re.compile(
                rf"{escaped_name}\s*[:：]?\s*([<>≈约]?\s*\d+(?:\.\d+)?)\s*({unit_part})?"
            )
        )
        patterns.append(
            re.compile(
                rf"([<>≈约]?\s*\d+(?:\.\d+)?)\s*({unit_part})\s*(?:的)?\s*{escaped_name}"
            )
        )
    else:
        patterns.append(re.compile(rf"{escaped_name}\s*[:：]?\s*([^\n，。,；;]+)"))
    return patterns


def indicator_matches_domain(indicator: IndicatorDef, domains: Sequence[str]) -> bool:
    if not indicator.allowed_domain_ids:
        return True
    return any(domain in indicator.allowed_domain_ids for domain in domains)


def extract_indicators(
    content: str,
    domains: Sequence[str],
    indicator_defs: Sequence[IndicatorDef],
    limit: int = 20,
) -> List[Tuple[str, str, str]]:
    results: List[Tuple[str, str, str]] = []
    seen = set()

    for indicator in indicator_defs:
        if not indicator_matches_domain(indicator, domains):
            continue
        for pattern in build_indicator_patterns(indicator):
            match = pattern.search(content)
            if not match:
                continue

            if indicator.data_type == "number":
                value = re.sub(r"\s+", "", match.group(1))
                unit = match.group(2) or indicator.unit_default
            else:
                value = match.group(1).strip()
                unit = indicator.unit_default

            key = (indicator.name, value, unit)
            if key in seen:
                continue
            seen.add(key)
            results.append((indicator.name, value, unit))
            break

        if len(results) >= limit:
            break

    return results


def heuristic_tags(title: str, content: str, domains: Sequence[str]) -> List[str]:
    text = f"{title}\n{content}"
    tags: List[str] = []
    if "吸附" in text:
        tags.append("吸附")
    if "吸收" in text:
        tags.append("吸收")
    if "膜" in text:
        tags.append("膜分离")
    if "电化学" in text:
        tags.append("电化学")
    if "矿化" in text:
        tags.append("矿化利用")
    if "封存" in text or "注入" in text:
        tags.append("地质封存")
    if "运输" in text or "管道" in text:
        tags.append("CO2运输")

    domain_name_map = {
        "DOM_CCUS_L2_CAPTURE": "捕集",
        "DOM_CCUS_L2_TRANSPORT": "运输",
        "DOM_CCUS_L2_UTILIZATION": "利用",
        "DOM_CCUS_L2_STORAGE": "封存",
        "DOM_CCUS_L2_SUPPORT": "支撑技术",
    }
    for domain in domains:
        name = domain_name_map.get(domain)
        if name and name not in tags:
            tags.append(name)

    return tags[:8] or ["CCUS"]


def heuristic_importance(title: str, content: str, indicators: Sequence[Tuple[str, str, str]]) -> int:
    text = f"{title}\n{content}"
    score = 2
    strong_markers = [
        "首次",
        "突破",
        "显著提升",
        "降低成本",
        "提高",
        "中试",
        "示范",
        "规模化",
        "产业化",
        "商业化",
    ]
    for marker in strong_markers:
        if marker in text:
            score += 1
    if len(indicators) >= 3:
        score += 1
    return max(1, min(score, 5))


def call_openai_json(
    api_key: str,
    model: str,
    title: str,
    content: str,
    domains: Sequence[str],
) -> Optional[Dict[str, object]]:
    prompt = f"""
你是 CCUS 情报结构化助手。请只返回 JSON，不要输出其他文字。

任务：
1. 判断该技术情报的重要度 importance_score，范围 1-5，5 为最高。
2. 生成 3-8 个中文 tags。

已知 domains: {list(domains)}
标题: {title}
正文: {content[:6000]}

JSON 格式：
{{
  "importance_score": 1,
  "tags": ["标签1", "标签2"]
}}
""".strip()

    payload = {
        "model": model,
        "input": prompt,
        "text": {"format": {"type": "json_object"}},
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except (error.HTTPError, error.URLError, TimeoutError):
        return None

    try:
        data = json.loads(raw)
        text = ""
        for item in data.get("output", []):
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    text += content_item.get("text", "")
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None

    return parsed


def enrich_with_ai(records: List[SectionRecord], model: str) -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return

    for record in records:
        result = call_openai_json(
            api_key=api_key,
            model=model,
            title=record.title,
            content=record.content,
            domains=record.domains,
        )
        if not result:
            continue
        score = result.get("importance_score")
        tags = result.get("tags")
        if isinstance(score, int) and 1 <= score <= 5:
            record.importance_score = score
        if isinstance(tags, list):
            record.tags = [str(tag).strip() for tag in tags if str(tag).strip()][:8]
        time.sleep(0.2)


def build_csv_row(record: SectionRecord) -> Dict[str, str]:
    row = {header: "" for header in CSV_HEADERS}
    row.update(
        {
            "title": record.title,
            "published_at": record.published_at,
            "source_url": "",
            "source_types": record.source_type,
            "info_types": "技术",
            "domains": ";".join(record.domains),
            "importance_score": str(record.importance_score),
            "is_new_tech": "false",
            "content": record.content,
            "tags": ";".join(record.tags),
            "classification": "内部",
            "comment": record.comment,
            "alert_manual": "false",
            "alert_title": "",
            "alert_body": "",
            "reviewer_comment": "",
            "duration": "",
            "custom_expires_on": "",
            "alert_color": "",
        }
    )
    for idx, (name, value, unit) in enumerate(record.indicators[:20], start=1):
        row[f"indicator_{idx}_name"] = name
        row[f"indicator_{idx}_value"] = value
        row[f"indicator_{idx}_unit"] = unit
    return row


def iter_pdf_files(input_dir: Path) -> Iterable[Path]:
    yield from sorted(input_dir.rglob("*.pdf"))


def process_pdfs(
    input_dir: Path,
    indicator_defs_path: Path,
    domains_path: Path,
    use_ai: bool,
    model: str,
) -> List[SectionRecord]:
    indicator_defs = load_indicator_defs(indicator_defs_path)
    domain_lookup = load_domain_lookup(domains_path)
    all_records: List[SectionRecord] = []

    for pdf_path in iter_pdf_files(input_dir):
        text = extract_pdf_text(pdf_path)
        records = extract_sections(text, pdf_path.name)
        for record in records:
            record.domains = infer_domains(record.title, record.content, domain_lookup)
            record.indicators = extract_indicators(
                record.content, record.domains, indicator_defs
            )
            record.tags = heuristic_tags(record.title, record.content, record.domains)
            record.importance_score = heuristic_importance(
                record.title, record.content, record.indicators
            )
        all_records.extend(records)

    if use_ai:
        enrich_with_ai(all_records, model=model)

    return all_records


def write_csv(records: Sequence[SectionRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for record in records:
            writer.writerow(build_csv_row(record))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 PDF 中提取 CCUS 相关内容并生成批量上传 CSV"
    )
    parser.add_argument("--input-dir", required=True, help="PDF 目录")
    parser.add_argument("--output", required=True, help="输出 CSV 文件路径")
    parser.add_argument(
        "--indicator-defs",
        default="data/indicator_defs.json",
        help="指标定义 JSON 路径",
    )
    parser.add_argument(
        "--domains-json",
        default="data/domains.json",
        help="领域定义 JSON 路径",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="若设置且存在 OPENAI_API_KEY，则用 AI 增强 importance_score 与 tags",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="AI 模型名，仅在 --use-ai 时生效",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    indicator_defs_path = Path(args.indicator_defs).expanduser().resolve()
    domains_path = Path(args.domains_json).expanduser().resolve()

    if not input_dir.exists():
        print(f"输入目录不存在: {input_dir}", file=sys.stderr)
        return 1

    records = process_pdfs(
        input_dir=input_dir,
        indicator_defs_path=indicator_defs_path,
        domains_path=domains_path,
        use_ai=args.use_ai,
        model=args.model,
    )
    write_csv(records, output_path)
    print(f"已生成 {len(records)} 条记录: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
