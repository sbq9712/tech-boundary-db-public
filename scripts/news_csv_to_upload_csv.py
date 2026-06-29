#!/usr/bin/env python3
"""
将 ccus_weekly_report.csv 转换为技术数据库批量上传格式的 CSV。

用法（纯规则，无需 API）：
  python3 scripts/news_csv_to_upload_csv.py \
    --input ccus_weekly_report.csv \
    --output ccus_upload_ready.csv

AI 增强（推荐，需设置 OPENAI_API_KEY）：
  python3 scripts/news_csv_to_upload_csv.py \
    --input ccus_weekly_report.csv \
    --output ccus_upload_ready.csv \
    --use-ai [--model gpt-4o-mini]

AI 会补全：domains（L4 精确分类）、info_types、is_new_tech、importance_score、tags、indicators。
无 AI 时退化为规则推断（L2 域 + 启发式打分）。
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
from typing import Dict, List, Optional, Tuple
from urllib import error, request

# ──────────────────────────────────────────────
# Unicode 下标数字 → 普通数字
# ──────────────────────────────────────────────
_SUB_TABLE = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

def normalize_subs(s: str) -> str:
    """Replace Unicode subscript digits (₀-₉) with normal digits."""
    return s.translate(_SUB_TABLE)


# ──────────────────────────────────────────────
# CSV 列头（与 upload_template.csv 完全一致）
# ──────────────────────────────────────────────
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
for _i in range(1, 21):
    CSV_HEADERS.extend(
        [f"indicator_{_i}_name", f"indicator_{_i}_value", f"indicator_{_i}_unit"]
    )

# ──────────────────────────────────────────────
# 月份缩写 → 数字
# ──────────────────────────────────────────────
MONTH_ABBR: Dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# ──────────────────────────────────────────────
# 日期正则
# ──────────────────────────────────────────────
# 完整日期：2025年3月24日 / 2025-03-24 / 2025/3/24
_DATE_FULL = re.compile(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})[日]?")
# 仅月日：3月24日 / 3-24（用于从 month 字段补全年份）
_DATE_MD = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日")

# ──────────────────────────────────────────────
# L2 级规则关键词（AI 不可用时的 fallback）
# ──────────────────────────────────────────────
_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    # 捕集/分离：包含富氧燃烧、制氢（作为碳捕集前处理）、生物质能+CCS
    "DOM_CCUS_L2_CAPTURE": [
        "捕集", "吸收", "吸附", "膜分离", "相变分离", "化学链",
        "直接空气捕集", "DAC", "富氧燃烧", "碳捕获", "碳捕集",
        "BECCS", "生物质碳捕", "船用碳捕", "移动碳捕",
        "氢气燃烧炉", "全氧燃烧",
    ],
    # 运输：CO2 管道/船运/槽车，含液化压缩
    "DOM_CCUS_L2_TRANSPORT": [
        "CO2运输", "CO₂运输", "碳管道", "CO2管道", "槽车", "液化CO2",
        "CO2船运", "LNG双燃料",  # LNG船与CO2运输基础设施相关
    ],
    # 利用：CO2 转化为产品，含制氢路线的CO2利用、生物炭CDR、矿化建材
    "DOM_CCUS_L2_UTILIZATION": [
        "CO2利用", "CO₂利用", "资源化", "矿化", "甲醇", "e-Methanol",
        "电催化还原", "驱油", "EOR", "合成燃料", "CDR", "负排放", "碳移除",
        "CO2制甲烷", "CO2加氢", "二氧化碳加氢", "CO2转化",
        "生物炭", "碳汇", "CO2固化", "碳酸钙", "混凝土固碳",
        "低碳铝", "低碳钢", "绿钢",  # 工业原料减碳属于CO2利用大背景
        "碳信用", "碳移除信用",
    ],
    # 封存：地质封存、矿物封存
    "DOM_CCUS_L2_STORAGE": [
        "封存", "咸水层", "地质封存", "CO2注入", "地下储存",
        "岩石封存", "玄武岩", "矿物封存", "增强风化",
    ],
    # 支撑技术：监测、压缩、纯化、传感、算力/数据中心（用于CCUS模拟/监测）
    "DOM_CCUS_L2_SUPPORT": [
        "监测", "传感", "压缩机", "换热器", "仿真", "控制系统",
        "算力", "数据中心", "海水冷却",  # 数据中心冷却归入支撑技术
        "绿电直连", "源网荷储",          # 为CCUS供能的电力保障
    ],
}


# ──────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────
@dataclass
class IndicatorDef:
    id: str
    name: str
    match_name: str
    unit_default: str
    data_type: str
    allowed_domain_ids: List[str]


@dataclass
class NewsRecord:
    title: str
    source_type: str       # 产业新闻 / 学术文献
    source_url: str
    month_raw: str         # e.g. "Mar-25"
    body: str
    comment: str
    # 以下由后处理填入
    published_at: str = ""
    domains: List[str] = field(default_factory=list)
    info_types: str = "技术"
    is_new_tech: bool = False
    importance_score: int = 3
    tags: List[str] = field(default_factory=list)
    indicators: List[Tuple[str, str, str]] = field(default_factory=list)


# ──────────────────────────────────────────────
# 数据加载
# ──────────────────────────────────────────────
def load_indicator_defs(path: Path) -> List[IndicatorDef]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    result = []
    for item in raw:
        if not item.get("is_active", False):
            continue
        result.append(IndicatorDef(
            id=item["id"],
            name=item["name"],
            match_name=item.get("match_name", item["name"]),
            unit_default=item.get("unit_default", ""),
            data_type=item.get("data_type", "string"),
            allowed_domain_ids=item.get("allowed_domain_ids", []),
        ))
    return result


def load_domains(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_l4_domain_list(domains_raw: List[Dict]) -> List[Dict[str, str]]:
    """返回 CCUS 体系内 L4 域的 [{id, path}] 列表，path 为 L2>L3>L4 层级名称。"""
    by_id = {d["id"]: d for d in domains_raw if d.get("is_active", False)}

    def ancestor_ids(node: Dict) -> List[str]:
        ids: List[str] = []
        cur = node
        while cur.get("parent_id"):
            parent = by_id.get(cur["parent_id"])
            if not parent:
                break
            ids.append(parent["id"])
            cur = parent
        return ids

    def ancestor_names(node: Dict) -> List[str]:
        names: List[str] = []
        cur = node
        while cur.get("parent_id"):
            parent = by_id.get(cur["parent_id"])
            if not parent:
                break
            names.append(parent["name"])
            cur = parent
        names.reverse()
        return names

    result = []
    for d in domains_raw:
        if d.get("level") == 4 and d.get("is_active", False):
            # 只保留祖先链中含 DOM_CCUS_L1 的域
            if "DOM_CCUS_L1" not in ancestor_ids(d):
                continue
            ancestors = ancestor_names(d)
            path = " > ".join(ancestors + [d["name"]])
            result.append({"id": d["id"], "path": path})
    return result


def build_l2_domain_lookup(domains_raw: List[Dict]) -> Dict[str, Dict]:
    return {d["id"]: d for d in domains_raw if d.get("is_active", False)}


# ──────────────────────────────────────────────
# 日期提取
# ──────────────────────────────────────────────
def parse_month_field(month_raw: str) -> Tuple[int, int]:
    """从 'Mar-25' 解析出 (year, month)，解析失败返回 (0, 0)。"""
    month_raw = month_raw.strip()
    m = re.match(r"([A-Za-z]{3})-(\d{2})", month_raw)
    if not m:
        return 0, 0
    abbr = m.group(1).capitalize()
    year = 2000 + int(m.group(2))
    month_num = MONTH_ABBR.get(abbr, 0)
    return year, month_num


def extract_date_from_text(
    text: str,
    source_type: str,
    month_raw: str,
) -> str:
    """
    产业新闻取前3句，学术文献取后3句。
    优先匹配完整日期，次之月日（用 month 字段补全年份）。
    均失败则返回 month 字段的 YYYY-MM-01。
    """
    # 按句分割（。！？…以及换行）
    sentences = re.split(r"[。！？…\n]+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if source_type == "产业新闻":
        candidates = sentences[:3]
    else:
        candidates = sentences[-3:]

    # 完整日期
    for sent in candidates:
        m = _DATE_FULL.search(sent)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # 仅月日 → 补年
    year_fallback, _ = parse_month_field(month_raw)
    for sent in candidates:
        m = _DATE_MD.search(sent)
        if m and year_fallback:
            mo, d = int(m.group(1)), int(m.group(2))
            return f"{year_fallback:04d}-{mo:02d}-{d:02d}"

    # fallback：month 字段
    year_fallback, mo_fallback = parse_month_field(month_raw)
    if year_fallback and mo_fallback:
        return f"{year_fallback:04d}-{mo_fallback:02d}-01"
    return ""


# ──────────────────────────────────────────────
# 规则 fallback（无 AI 时使用）
# ──────────────────────────────────────────────
def infer_domains_rule(
    title: str, body: str, domain_lookup: Dict[str, Dict]
) -> List[str]:
    text = f"{title}\n{body}"
    scores: Dict[str, int] = {}
    for dom_id, keywords in _DOMAIN_KEYWORDS.items():
        sc = sum(text.count(kw) for kw in keywords)
        if sc > 0 and dom_id in domain_lookup:
            scores[dom_id] = sc
    if not scores:
        return ["DOM_CCUS_L1"]  # 无法细分时归入 CCUS 顶层
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [dom for dom, _ in ranked[:2]]


_IMPORTANCE_MARKERS = [
    "首次", "突破", "显著", "大幅", "中试", "示范项目",
    "规模化", "产业化", "商业化", "里程碑", "协议",
]

def heuristic_importance(title: str, body: str, n_indicators: int) -> int:
    text = f"{title}\n{body}"
    score = 3
    for marker in _IMPORTANCE_MARKERS:
        if marker in text:
            score += 1
    if n_indicators >= 3:
        score += 1
    return max(1, min(score, 10))


_TAG_RULES: List[Tuple[str, str]] = [
    ("吸附", "吸附捕集"),
    ("吸收", "吸收捕集"),
    ("膜分离", "膜分离"),
    ("电化学", "电化学"),
    ("矿化", "矿化利用"),
    ("封存", "地质封存"),
    ("运输", "CO2运输"),
    ("管道", "CO2运输"),
    ("甲醇", "CO2制甲醇"),
    ("BECCS", "BECCS"),
    ("DAC", "直接空气捕集"),
    ("驱油", "CO2-EOR"),
]

def heuristic_tags(title: str, body: str) -> List[str]:
    text = f"{title}\n{body}"
    tags = [tag for kw, tag in _TAG_RULES if kw in text]
    seen: List[str] = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return seen[:8] or ["CCUS"]


# 规则指标提取（复用 pdf 脚本逻辑）
_UNIT_PAT = (
    r"GJ/tCO[₂2]|kWh/tCO[₂2]|gCO[₂2]/g·h|gCO[₂2]/g|Mt/年|万吨/年|万吨"
    r"|元/kg|元/t(?!CO)|元/tCO2|元/tCO[₂2]|元/km|元/t·km"
    r"|km|MPa|℃|%/年|%|m(?!\w)|t/天|年|圈|kW|RMB"
)


def extract_indicators_rule(
    body: str,
    domains: List[str],
    defs: List[IndicatorDef],
) -> List[Tuple[str, str, str]]:
    results: List[Tuple[str, str, str]] = []
    seen = set()
    for ind in defs:
        allowed = ind.allowed_domain_ids
        if allowed and not any(d in allowed for d in domains):
            continue
        escaped = re.escape(ind.match_name)
        if ind.data_type == "number":
            unit_part = re.escape(ind.unit_default) if ind.unit_default else _UNIT_PAT
            patterns = [
                re.compile(rf"{escaped}\s*[:：]?\s*([<>≈约]?\s*\d+(?:\.\d+)?)\s*({unit_part})?"),
                re.compile(rf"([<>≈约]?\s*\d+(?:\.\d+)?)\s*({unit_part})\s*(?:的)?\s*{escaped}"),
            ]
        else:
            patterns = [re.compile(rf"{escaped}\s*[:：]?\s*([^\n，。,；;]{{1,30}})")]
        for pat in patterns:
            m = pat.search(body)
            if not m:
                continue
            if ind.data_type == "number":
                value = re.sub(r"\s+", "", m.group(1))
                unit = m.group(2) if m.lastindex >= 2 and m.group(2) else ind.unit_default
            else:
                value = m.group(1).strip()
                unit = ind.unit_default
            key = (ind.name, value)
            if key in seen:
                continue
            seen.add(key)
            results.append((ind.name, value, unit))
            break
        if len(results) >= 20:
            break
    return results


# ──────────────────────────────────────────────
# OpenAI API 调用（/v1/chat/completions）
# ──────────────────────────────────────────────
def _build_system_prompt(
    l4_domains: List[Dict[str, str]],
    indicator_defs: List[IndicatorDef],
) -> str:
    domain_lines = "\n".join(
        f'  {d["id"]} : {d["path"]}' for d in l4_domains
    )
    ind_lines = "\n".join(
        f'  {ind.name}（单位: {ind.unit_default or "文本"}）' for ind in indicator_defs
    )
    return f"""你是 CCUS 技术数据库录入助手，负责将产业新闻或学术文献结构化。

所有条目必须归入 CCUS 体系，即下方列表中的域。即使文章主题不是严格意义上的 CCUS（如氢能制备、低碳材料、绿电等），也要选择 CCUS 体系内语义最接近的子域。

## 可选 L4 域列表（仅限以下 CCUS 域，选 1-3 个最匹配的 id）
{domain_lines}

## 可提取的指标定义（若文中有对应数值则提取，无则不填）
{ind_lines}

## 输出格式（严格 JSON，不加任何注释）
{{
  "published_at": "YYYY-MM-DD 或空字符串",
  "domains": ["DOM_xxx"],
  "info_types": "技术 或 政策 或 市场 或 项目",
  "is_new_tech": true/false,
  "importance_score": 1-10,
  "tags": ["标签1", ...],
  "indicators": [
    {{"name": "指标名（与定义完全一致）", "value": "数值或文本", "unit": "单位"}},
    ...
  ]
}}

## 说明
- published_at：产业新闻从正文第一句提取，学术文献从最后一句提取；仅有月日时补全为提示中的参考年份；找不到则留空
- importance_score：1=背景介绍，5=中等技术进展，8=重大突破或里程碑，10=颠覆性
- is_new_tech：true 表示涉及新型技术路线或首次报道的技术
- tags：3-8 个中文关键词"""


def call_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_content: str,
) -> Optional[Dict]:
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except (error.HTTPError, error.URLError, TimeoutError) as e:
        print(f"  [AI 请求失败] {e}", file=sys.stderr)
        return None
    try:
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  [AI 响应解析失败] {e}", file=sys.stderr)
        return None


def apply_ai_result(record: NewsRecord, result: Dict, defs: List[IndicatorDef]) -> None:
    """将 AI 返回的 JSON 写入 record，保留类型安全。"""
    if result.get("published_at") and not record.published_at:
        record.published_at = str(result["published_at"])

    domains = result.get("domains")
    if isinstance(domains, list) and domains:
        record.domains = [str(d).strip() for d in domains if str(d).strip()]

    info_types = result.get("info_types")
    if isinstance(info_types, str) and info_types.strip():
        record.info_types = info_types.strip()

    record.is_new_tech = bool(result.get("is_new_tech", False))

    score = result.get("importance_score")
    if isinstance(score, (int, float)) and 1 <= score <= 10:
        record.importance_score = int(score)

    tags = result.get("tags")
    if isinstance(tags, list):
        record.tags = [str(t).strip() for t in tags if str(t).strip()][:8]

    ind_raw = result.get("indicators")
    if isinstance(ind_raw, list):
        valid_names = {d.name for d in defs}
        inds: List[Tuple[str, str, str]] = []
        for item in ind_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            value = str(item.get("value", "")).strip()
            unit = str(item.get("unit", "")).strip()
            if name and value and name in valid_names:
                inds.append((name, value, unit))
        if inds:
            record.indicators = inds[:20]


# ──────────────────────────────────────────────
# 主处理流程
# ──────────────────────────────────────────────
def process_records(
    input_path: Path,
    indicator_defs: List[IndicatorDef],
    domains_raw: List[Dict],
    use_ai: bool,
    model: str,
) -> List[NewsRecord]:
    l4_domains = build_l4_domain_list(domains_raw)
    l2_lookup = build_l2_domain_lookup(domains_raw)
    api_key = os.getenv("OPENAI_API_KEY", "").strip() if use_ai else ""
    system_prompt = _build_system_prompt(l4_domains, indicator_defs) if api_key else ""

    records: List[NewsRecord] = []

    with input_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        title = normalize_subs(row.get("title", "").strip())
        body = normalize_subs(row.get("body", "").strip())
        source = row.get("source", "").strip()
        comments = normalize_subs(row.get("comments", "").strip())
        source_type = row.get("type", "产业新闻").strip()
        month_raw = row.get("month", "").strip()

        print(f"[{idx}/{total}] {title[:40]}...", file=sys.stderr)

        rec = NewsRecord(
            title=title,
            source_type=source_type,
            source_url=source,
            month_raw=month_raw,
            body=body,
            comment=comments,
        )

        # 1. 日期提取（正文 → month 字段 fallback）
        rec.published_at = extract_date_from_text(body, source_type, month_raw)

        # 2. AI 路径
        if api_key:
            ref_year, _ = parse_month_field(month_raw)
            user_content = (
                f"参考年份（用于补全仅有月日的日期）：{ref_year}\n"
                f"来源类型：{source_type}\n"
                f"标题：{title}\n"
                f"正文：{body}\n"
                f"备注：{comments}"
            )
            result = call_openai(api_key, model, system_prompt, user_content)
            if result:
                apply_ai_result(rec, result, indicator_defs)
            time.sleep(0.3)  # 限速保护

        # 3. 未被 AI 填充的字段用规则补全
        if not rec.domains:
            rec.domains = infer_domains_rule(title, body, l2_lookup)
        if not rec.indicators:
            rec.indicators = extract_indicators_rule(body, rec.domains, indicator_defs)
        if not rec.tags:
            rec.tags = heuristic_tags(title, body)
        if rec.importance_score == 3 and not api_key:
            rec.importance_score = heuristic_importance(title, body, len(rec.indicators))

        records.append(rec)

    return records


# ──────────────────────────────────────────────
# CSV 输出
# ──────────────────────────────────────────────
def build_row(rec: NewsRecord) -> Dict[str, str]:
    row = {h: "" for h in CSV_HEADERS}
    row.update({
        "title": rec.title,
        "published_at": rec.published_at,
        "source_url": rec.source_url,
        "source_types": rec.source_type,
        "info_types": rec.info_types,
        "domains": ";".join(rec.domains),
        "importance_score": str(rec.importance_score),
        "is_new_tech": "true" if rec.is_new_tech else "false",
        "content": rec.body,
        "tags": ";".join(rec.tags),
        "classification": "内部",
        "comment": rec.comment,
        "alert_manual": "false",
    })
    for i, (name, value, unit) in enumerate(rec.indicators[:20], start=1):
        row[f"indicator_{i}_name"] = name
        row[f"indicator_{i}_value"] = value
        row[f"indicator_{i}_unit"] = unit
    return row


def write_csv(records: List[NewsRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for rec in records:
            writer.writerow(build_row(rec))


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 ccus_weekly_report.csv 转换为批量上传格式 CSV"
    )
    parser.add_argument("--input", required=True, help="输入 CSV 路径")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")
    parser.add_argument(
        "--indicator-defs",
        default="data/indicator_defs.json",
        help="指标定义 JSON（默认 data/indicator_defs.json）",
    )
    parser.add_argument(
        "--domains-json",
        default="data/domains.json",
        help="域定义 JSON（默认 data/domains.json）",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="启用 AI 增强（需设置 OPENAI_API_KEY）",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="AI 模型（默认 gpt-4o-mini）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    ind_path = Path(args.indicator_defs).expanduser().resolve()
    dom_path = Path(args.domains_json).expanduser().resolve()

    if not input_path.exists():
        print(f"输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    indicator_defs = load_indicator_defs(ind_path)
    domains_raw = load_domains(dom_path)

    if args.use_ai and not os.getenv("OPENAI_API_KEY"):
        print("警告：--use-ai 已指定但未找到 OPENAI_API_KEY，将退化为纯规则模式。", file=sys.stderr)

    records = process_records(
        input_path=input_path,
        indicator_defs=indicator_defs,
        domains_raw=domains_raw,
        use_ai=args.use_ai,
        model=args.model,
    )
    write_csv(records, output_path)
    print(f"\n完成：共输出 {len(records)} 条记录 → {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
