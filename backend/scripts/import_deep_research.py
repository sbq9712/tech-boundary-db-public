#!/usr/bin/env python3
"""
Register knowledge-base documents as knowledge_artifacts and seed a minimal
technology_node / parameter_observation index for frontend dashboards.

The source of truth is external-data/knowledge-base/*.md frontmatter. This
script is idempotent: artifacts are upserted by stable_id and generated
parameters by stable_id.
"""
from __future__ import annotations

import hashlib
import argparse
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:
    from app.db.session import SessionLocal
    from app.models.knowledge_node import IndustryNode, TechnologyNode
    from app.models.knowledge_artifact import KnowledgeArtifact
    from app.models.parameter_observation import ParameterObservation
    HAS_DB = True
except ImportError:
    HAS_DB = False

KB_BASE = Path("/knowledge-base")  # inside container

# Preserve stable IDs already used by the first 9 dashboard artifacts.
LEGACY_ARTIFACT_IDS = {
    "SOC/SOFC行业深度报告.md": "ART-20260712-4F444B2861",
    "压缩空气储能/压缩空气储能_长时储能技术边界.md": "ART-20260709-CAES",
    "超导材料/超导材料_REBCO高温超导带材技术边界.md": "ART-20260709-REBCO",
    "脑机接口/脑机接口_侵入式神经接口技术边界.md": "ART-20260709-BCI",
    "钠电池/钠电池_钠离子电池储能技术边界.md": "ART-20260709-NAION",
    "航天/航天_可重复使用火箭技术边界.md": "ART-20260709-SPACE",
    "光热/光热_光热发电与熔盐储热技术边界.md": "ART-20260709-CSP",
    "热泵/热泵_高温热泵工业脱碳技术边界.md": "ART-20260709-HTHP",
    "合成氨和绿氨/合成氨和绿氨_柔性电解制氨技术边界.md": "ART-20260709-NH3",
    "具身智能/具身智能_人形机器人技术边界.md": "ART-20260709-HUMANOID",
}

LEGACY_TECH_IDS = {
    "SOC/SOFC行业深度报告.md": "tech_3ba258d5d911656f",
    "压缩空气储能/压缩空气储能_长时储能技术边界.md": "tech_caes",
    "超导材料/超导材料_REBCO高温超导带材技术边界.md": "tech_rebco",
    "脑机接口/脑机接口_侵入式神经接口技术边界.md": "tech_bci",
    "钠电池/钠电池_钠离子电池储能技术边界.md": "tech_na_ion",
    "航天/航天_可重复使用火箭技术边界.md": "tech_reusable_rocket",
    "光热/光热_光热发电与熔盐储热技术边界.md": "tech_csp",
    "热泵/热泵_高温热泵工业脱碳技术边界.md": "tech_hthp",
    "合成氨和绿氨/合成氨和绿氨_柔性电解制氨技术边界.md": "tech_green_nh3",
    "具身智能/具身智能_人形机器人技术边界.md": "tech_humanoid",
}

SKIP_DOC_NAMES = {"_知识库文档规范.md", "_文献索引.md", "专利地图.md", "专利清单.md", "技术摘要_中文.md", "技术摘要_关键元件.md"}


@dataclass
class KBDocument:
    path: Path
    vault_path: str
    title: str
    taxonomy_leaf: str
    status: str = "active"
    version: str = "1.0"
    parameters: list[dict] = field(default_factory=list)


def _hash(text: str, n: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n].upper()


def stable_artifact_id(vault_path: str) -> str:
    return LEGACY_ARTIFACT_IDS.get(vault_path, f"ART-20260712-{_hash(vault_path, 10)}")


def stable_tech_node_id(taxonomy_leaf: str) -> str:
    return f"tech_{hashlib.sha1(taxonomy_leaf.encode('utf-8')).hexdigest()[:16]}"


def _tech_node_id(doc: KBDocument) -> str:
    return LEGACY_TECH_IDS.get(doc.vault_path, stable_tech_node_id(doc.taxonomy_leaf or doc.title))


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"\'')
    return data


def _section(text: str, marker: str) -> str:
    m = re.search(rf"^##\s+.*{re.escape(marker)}.*$", text, flags=re.M)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], flags=re.M)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end]


def _parse_tables(md: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = [ln.strip() for ln in md.splitlines() if ln.strip().startswith("|")]
    i = 0
    while i + 1 < len(lines):
        headers = [c.strip() for c in lines[i].strip("|").split("|")]
        sep = [c.strip() for c in lines[i + 1].strip("|").split("|")]
        if not sep or not all(set(c) <= {"-", ":", " "} for c in sep):
            i += 1
            continue
        i += 2
        while i < len(lines):
            cells = [re.sub(r"\*\*(.+?)\*\*", r"\1", c.strip()) for c in lines[i].strip("|").split("|")]
            if len(cells) != len(headers):
                break
            rows.append(dict(zip(headers, cells)))
            i += 1
        continue
    return rows


def _parameter_type(name: str) -> str:
    if any(k in name for k in ["成本", "CAPEX", "价格", "投资", "市场", "份额", "产能", "交货", "周期"]):
        return "economic"
    if any(k in name for k in ["客户", "订单", "生态", "商业"]):
        return "commercial"
    return "technical"


def _parse_parameters(text: str) -> list[dict]:
    sec = _section(text, "§2") or _section(text, "关键指标")
    params: list[dict] = []
    for row in _parse_tables(sec):
        name = row.get("指标") or row.get("关键指标") or row.get("参数")
        if not name or name in {"指标", "关键指标"}:
            continue
        value = row.get("实际值/公开披露") or row.get("当前最佳值") or row.get("当前实测") or row.get("当前实测/披露") or row.get("当前基线") or ""
        data_status = row.get("数据状态") or row.get("可信度") or ""
        if "?" in data_status or "❓" in data_status:
            verification_status = "disputed"
        elif "✓" in data_status or "✅" in data_status:
            verification_status = "human_checked"
        else:
            verification_status = "machine_extracted"
        unit = ""
        params.append({
            "parameter_name": name[:200],
            "parameter_type": _parameter_type(name),
            "value_text": value[:500] if value else None,
            "unit": unit,
            "condition_text": (row.get("条件/口径") or row.get("测试条件") or row.get("应用场景") or "")[:1000],
            "verification_status": verification_status,
            "notes": (row.get("进一步调研方向") or row.get("备注") or row.get("来源") or row.get("理论值/物理边界") or row.get("边界（理论/工程极限）") or "")[:1000],
        })
    return params[:12]


def discover_kb_documents(kb_base: Path = KB_BASE) -> list[KBDocument]:
    docs: list[KBDocument] = []
    for path in sorted(kb_base.rglob("*.md")):
        if path.name in SKIP_DOC_NAMES or "文献" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        title = fm.get("title", "").strip()
        taxonomy_leaf = fm.get("taxonomy_leaf", "").strip()
        if not title or not taxonomy_leaf:
            continue
        status = fm.get("status", "active").split("#", 1)[0].strip() or "active"
        if status not in {"active", "archived", "superseded"}:
            status = "active"
        vault_path = path.relative_to(kb_base).as_posix()
        docs.append(KBDocument(
            path=path,
            vault_path=vault_path,
            title=title,
            taxonomy_leaf=taxonomy_leaf,
            status=status,
            version=fm.get("version", "1.0"),
            parameters=_parse_parameters(text),
        ))
    return docs


def _find_ind_node_id(db, taxonomy_leaf: str) -> str | None:
    leaf_name = taxonomy_leaf.split("/")[-1] if taxonomy_leaf else ""
    for term in [taxonomy_leaf.replace("/", ">"), taxonomy_leaf, leaf_name]:
        if not term:
            continue
        node = db.query(IndustryNode).filter(IndustryNode.description.like(f"%{term}%")).first()
        if node:
            return node.id
        node = db.query(IndustryNode).filter(IndustryNode.name == term).first()
        if node:
            return node.id
    return None


def run(vault_paths: set[str] | None = None):
    if not HAS_DB:
        print("ERROR: no DB access (run inside api container)", file=sys.stderr)
        return 1

    docs = discover_kb_documents(KB_BASE)
    if vault_paths:
        docs = [doc for doc in docs if doc.vault_path in vault_paths]
        missing = vault_paths - {doc.vault_path for doc in docs}
        if missing:
            print(f"ERROR: requested knowledge-base documents not found: {sorted(missing)}", file=sys.stderr)
            return 1
    db = SessionLocal()
    try:
        tech_imported = tech_updated = 0
        art_imported = art_updated = 0
        param_imported = 0

        for doc in docs:
            tech_id = _tech_node_id(doc)
            tech = db.query(TechnologyNode).filter(TechnologyNode.id == tech_id).first()
            if not tech:
                tech = TechnologyNode(
                    id=tech_id,
                    name=doc.title.replace("_技术边界", "").replace("_", " "),
                    parent_id=None,
                    node_type="route",
                    description=f"KB taxonomy leaf: {doc.taxonomy_leaf}",
                    aliases=[doc.taxonomy_leaf.split("/")[-1]],
                    status="active",
                )
                db.add(tech)
                tech_imported += 1
            else:
                tech.name = tech.name or doc.title
                tech.description = f"KB taxonomy leaf: {doc.taxonomy_leaf}"
                tech.status = "active"
                tech_updated += 1

            stable_id = stable_artifact_id(doc.vault_path)
            ind_id = _find_ind_node_id(db, doc.taxonomy_leaf)
            art = db.query(KnowledgeArtifact).filter(KnowledgeArtifact.stable_id == stable_id).first()
            if not art:
                art = KnowledgeArtifact(
                    id=uuid.uuid4(),
                    stable_id=stable_id,
                    artifact_type="deep_research_note",
                    title=doc.title,
                    vault_path=doc.vault_path,
                    absolute_path=str(KB_BASE / doc.vault_path),
                    related_tech_node_ids=[tech_id],
                    related_ind_node_ids=[ind_id] if ind_id else [],
                    related_intelligence_ids=[],
                    related_observation_ids=[],
                    status=doc.status,
                    version=doc.version,
                    owner="赫米",
                )
                db.add(art)
                art_imported += 1
            else:
                art.title = doc.title
                art.vault_path = doc.vault_path
                art.absolute_path = str(KB_BASE / doc.vault_path)
                art.related_tech_node_ids = [tech_id]
                art.related_ind_node_ids = [ind_id] if ind_id else []
                art.status = doc.status
                art.version = doc.version
                art_updated += 1

            # The legacy 9 docs already have curated parameter rows; do not duplicate them.
            if doc.vault_path in LEGACY_ARTIFACT_IDS:
                continue
            for i, param_data in enumerate(doc.parameters):
                param_stable_id = f"{stable_id}-P{i+1:03d}"
                existing_param = db.query(ParameterObservation).filter(
                    ParameterObservation.stable_id == param_stable_id
                ).first()
                if not existing_param:
                    db.add(ParameterObservation(
                        stable_id=param_stable_id,
                        technology_node_id=tech_id,
                        parameter_name=param_data["parameter_name"],
                        parameter_type=param_data["parameter_type"],
                        value_text=param_data.get("value_text"),
                        unit=param_data.get("unit", ""),
                        condition_text=param_data.get("condition_text", ""),
                        scenario="深度调研",
                        extraction_confidence="medium",
                        verification_status=param_data.get("verification_status", "machine_extracted"),
                        notes=param_data.get("notes", ""),
                    ))
                    param_imported += 1
                else:
                    # Keep imported observations in sync with the source note.
                    # The stable id is positional inside §2, so edits should
                    # update the row instead of leaving stale dashboard values.
                    existing_param.technology_node_id = tech_id
                    existing_param.parameter_name = param_data["parameter_name"]
                    existing_param.parameter_type = param_data["parameter_type"]
                    existing_param.value_text = param_data.get("value_text")
                    existing_param.unit = param_data.get("unit", "")
                    existing_param.condition_text = param_data.get("condition_text", "")
                    existing_param.verification_status = param_data.get("verification_status", "machine_extracted")
                    existing_param.notes = param_data.get("notes", "")

        db.commit()
        print(
            f"Done: docs={len(docs)}, tech_nodes={tech_imported} imported/{tech_updated} updated, "
            f"artifacts={art_imported} imported/{art_updated} updated, parameters={param_imported} imported"
        )
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import deep-research knowledge-base documents")
    parser.add_argument(
        "--vault-path",
        action="append",
        default=[],
        help="Import only this knowledge-base-relative Markdown path; repeat as needed",
    )
    args = parser.parse_args()
    sys.exit(run(set(args.vault_path) or None))
