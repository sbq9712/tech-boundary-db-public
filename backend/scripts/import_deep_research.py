#!/usr/bin/env python3
"""
Register knowledge-base documents as knowledge_artifacts, and load key
parameters from those documents into parameter_observations.

Also seeds technology_nodes for the three deep-research tracks.

Idempotent: safe to re-run, uses upsert by stable_id.
"""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
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

# ─── Track definitions ──────────────────────────────────────────────

TRACKS = [
    {
        "doc_dir": "压缩空气储能",
        "doc_file": "压缩空气储能_长时储能技术边界.md",
        "tech_node_id": "tech_caes",
        "tech_node_name": "压缩空气储能 (CAES)",
        "tech_node_aliases": ["CAES", "A-CAES", "AA-CAES", "compressed air energy storage"],
        "ind_node_name": "压缩空气",
        "artifact_stable_id": "ART-20260709-CAES",
        "artifact_title": "压缩空气储能_长时储能技术边界",
        "dashboard": {
            "id": "caes",
            "name": "压缩空气储能 (CAES)",
            "scope": "长时储能、电网调峰、盐穴/地面储气",
            "status": "重点研究",
        },
        "parameters": [
            {"parameter_name": "系统往返效率（补燃式）", "parameter_type": "technical", "value_text": "42-54%", "unit": "%",
             "condition_text": "Huntorf/McIntosh 电厂实测", "verification_status": "human_checked",
             "notes": "η = W_out/(W_in+Q_fuel)，含燃料能量"},
            {"parameter_name": "系统往返效率（A-CAES）", "parameter_type": "technical", "value_min": 65, "value_max": 70, "unit": "%",
             "condition_text": "张家口100MW设计值", "verification_status": "human_checked",
             "notes": "绝热蓄热回收压缩热，无燃料消耗"},
            {"parameter_name": "单位储能成本（100MW+）", "parameter_type": "economic", "value_text": "~120", "unit": "USD/kWh",
             "condition_text": "2024年大型项目", "verification_status": "machine_extracted",
             "notes": "Yang et al. 2025 iScience，学习率15%"},
            {"parameter_name": "涡轮功率成本", "parameter_type": "economic", "value_min": 600, "value_max": 900, "unit": "USD/kW",
             "verification_status": "machine_extracted",
             "notes": "缺乏专为A-CAES优化的成熟涡轮机"},
            {"parameter_name": "储能成本（盐穴）", "parameter_type": "economic", "value_min": 5, "value_max": 15, "unit": "USD/kWh",
             "verification_status": "human_checked",
             "notes": "依赖地质条件，盐穴最低"},
            {"parameter_name": "储能成本（地面钢罐）", "parameter_type": "economic", "value_min": 50, "value_max": 100, "unit": "USD/kWh",
             "verification_status": "human_checked",
             "notes": "无地质约束但成本高"},
            {"parameter_name": "A-CAES 学习率", "parameter_type": "economic", "value_text": "~15", "unit": "%",
             "verification_status": "machine_extracted",
             "notes": "每倍增产能成本降低15%"},
        ],
    },
    {
        "doc_dir": "超导材料",
        "doc_file": "超导材料_REBCO高温超导带材技术边界.md",
        "tech_node_id": "tech_rebco",
        "tech_node_name": "REBCO 高温超导带材",
        "tech_node_aliases": ["REBCO", "HTS tape", "2G HTS", "coated conductor"],
        "ind_node_name": "超导材料",
        "artifact_stable_id": "ART-20260709-REBCO",
        "artifact_title": "超导材料_REBCO高温超导带材技术边界",
        "dashboard": {
            "id": "rebco",
            "name": "REBCO 高温超导带材",
            "scope": "聚变磁体、超高场MRI、超导输电",
            "status": "重点研究",
        },
        "parameters": [
            {"parameter_name": "临界电流 Ic（实验室短样）", "parameter_type": "technical", "value_text": "1836", "unit": "A/4mm",
             "condition_text": "4.2K, 20T, B‖c, Advanced MOCVD", "verification_status": "human_checked",
             "notes": "Selvamanickam IREF25，商业PLD的3.2倍"},
            {"parameter_name": "工程临界电流密度 Jce", "parameter_type": "technical", "value_text": "0.152", "unit": "MA/cm²",
             "condition_text": "77K, 自场, 热压银扩散", "verification_status": "human_checked",
             "notes": "Yu et al. 2026，提升68.1%"},
            {"parameter_name": "商业标准带 Ic", "parameter_type": "technical", "value_min": 400, "value_max": 500, "unit": "A/4mm",
             "condition_text": "4.2K, 15T, B‖c", "verification_status": "human_checked",
             "notes": "SuperPower HM tape"},
            {"parameter_name": "HTS 带材成本", "parameter_type": "economic", "value_text": "~125", "unit": "USD/kA-m",
             "verification_status": "machine_extracted",
             "notes": "大规模应用目标 <$10/kA-m，需10×降低"},
            {"parameter_name": "连续长度", "parameter_type": "technical", "value_text": "~500", "unit": "m",
             "verification_status": "human_checked",
             "notes": "Faraday Factory标准交付，存在Ic dropouts"},
            {"parameter_name": "中子辐照寿命阈值", "parameter_type": "technical", "value_text": "3×10²²", "unit": "n/m²",
             "condition_text": "14 MeV中子", "verification_status": "human_checked",
             "notes": "对应~9年运行，低于30年目标"},
            {"parameter_name": "Faraday Factory 年产能", "parameter_type": "economic", "value_text": "3000+", "unit": "km/yr@4mm",
             "verification_status": "machine_extracted",
             "notes": "全球最大2G HTS供应商"},
            {"parameter_name": "单台紧凑聚变所需带材", "parameter_type": "economic", "value_text": "~20000", "unit": "km",
             "verification_status": "human_checked",
             "notes": "标准带；高Ic带可减至5000km"},
        ],
    },
    {
        "doc_dir": "脑机接口",
        "doc_file": "脑机接口_侵入式神经接口技术边界.md",
        "tech_node_id": "tech_bci",
        "tech_node_name": "脑机接口 (BCI)",
        "tech_node_aliases": ["BCI", "brain-computer interface", "neural interface", "脑机接口"],
        "ind_node_name": "脑机接口",
        "artifact_stable_id": "ART-20260709-BCI",
        "artifact_title": "脑机接口_侵入式神经接口技术边界",
        "dashboard": {
            "id": "bci",
            "name": "脑机接口 (BCI)",
            "scope": "侵入式神经接口、通信恢复、运动解码",
            "status": "重点研究",
        },
        "parameters": [
            {"parameter_name": "信息传输速率 ICR", "parameter_type": "technical", "value_text": "9.5", "unit": "bits/sec",
             "condition_text": "Neuralink N1, 1024通道", "verification_status": "machine_extracted",
             "notes": "企业声明，接近人类输出带宽~10bps"},
            {"parameter_name": "通道数", "parameter_type": "technical", "value_text": "1024", "unit": "通道",
             "condition_text": "N1植入", "verification_status": "machine_extracted",
             "notes": "下一代目标3000通道"},
            {"parameter_name": "电极记录成功率", "parameter_type": "technical", "value_text": "35.6", "unit": "%",
             "condition_text": "Utah阵列, 14名受试者平均", "verification_status": "human_checked",
             "notes": "BrainGate长期数据"},
            {"parameter_name": "累计使用时间", "parameter_type": "technical", "value_text": "4900+", "unit": "小时",
             "condition_text": "21名受试者合计", "verification_status": "machine_extracted",
             "notes": "零严重器械相关不良事件（企业声明）"},
            {"parameter_name": "信号维持时间", "parameter_type": "technical", "value_min": 2.5, "value_max": 5, "unit": "年",
             "verification_status": "human_checked",
             "notes": "胶质疤痕导致信号衰减，生物限制"},
            {"parameter_name": "原始数据率", "parameter_type": "technical", "value_text": "~200", "unit": "Mbps",
             "condition_text": "1024ch×20kHz", "verification_status": "human_checked",
             "notes": "无线传输瓶颈，仅~1Mbps可传出"},
            {"parameter_name": "ICR vs 电极数关系", "parameter_type": "technical", "value_text": "对数增长", "unit": "—",
             "verification_status": "human_checked",
             "notes": "BrainGate外推，1024ch接近健全人鼠标水平"},
            {"parameter_name": "语音解码延迟", "parameter_type": "technical", "value_text": "数秒", "unit": "秒",
             "condition_text": "VOICE试验", "verification_status": "machine_extracted",
             "notes": "目标140wpm，当前未达标"},
        ],
    },
]


def _find_ind_node_id(db, name: str) -> str | None:
    """Find industry node by name (leaf or any level)."""
    node = db.query(IndustryNode).filter(IndustryNode.name == name).first()
    if node:
        return node.id
    # Try aliases / partial match
    node = db.query(IndustryNode).filter(
        IndustryNode.description.like(f"%{name}%")
    ).first()
    return node.id if node else None


def run():
    if not HAS_DB:
        print("ERROR: no DB access (run inside api container)", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        tech_imported = 0
        art_imported = 0
        param_imported = 0

        for track in TRACKS:
            # 1. Create/update technology node
            tech = db.query(TechnologyNode).filter(
                TechnologyNode.id == track["tech_node_id"]
            ).first()
            ind_id = _find_ind_node_id(db, track["ind_node_name"])

            if not tech:
                tech = TechnologyNode(
                    id=track["tech_node_id"],
                    name=track["tech_node_name"],
                    parent_id=None,
                    node_type="route",
                    description=f"Technology route: {track['tech_node_name']}",
                    aliases=track["tech_node_aliases"],
                    status="active",
                )
                db.add(tech)
                tech_imported += 1

            # 2. Register knowledge artifact
            doc_path = KB_BASE / track["doc_dir"] / track["doc_file"]
            stable_id = track["artifact_stable_id"]
            existing_art = db.query(KnowledgeArtifact).filter(
                KnowledgeArtifact.stable_id == stable_id
            ).first()

            if not existing_art:
                art = KnowledgeArtifact(
                    id=uuid.uuid4(),
                    stable_id=stable_id,
                    artifact_type="deep_research_note",
                    title=track["artifact_title"],
                    vault_path=f"{track['doc_dir']}/{track['doc_file']}",
                    absolute_path=str(doc_path),
                    related_tech_node_ids=[track["tech_node_id"]],
                    related_ind_node_ids=[ind_id] if ind_id else [],
                    related_intelligence_ids=[],
                    related_observation_ids=[],
                    status="active",
                    version="1.0",
                    owner="赫米",
                )
                db.add(art)
                art_imported += 1

            # 3. Load parameters
            for i, param_data in enumerate(track["parameters"]):
                param_stable_id = f"{track['tech_node_id'].upper()}-P{i+1:03d}"
                existing_param = db.query(ParameterObservation).filter(
                    ParameterObservation.stable_id == param_stable_id
                ).first()

                if not existing_param:
                    param = ParameterObservation(
                        stable_id=param_stable_id,
                        technology_node_id=track["tech_node_id"],
                        parameter_name=param_data["parameter_name"],
                        parameter_type=param_data["parameter_type"],
                        value_min=param_data.get("value_min"),
                        value_max=param_data.get("value_max"),
                        value_text=param_data.get("value_text"),
                        unit=param_data.get("unit", ""),
                        condition_text=param_data.get("condition_text", ""),
                        scenario="深度调研" if param_data["parameter_type"] == "economic" else "",
                        extraction_confidence="high",
                        verification_status=param_data.get("verification_status", "machine_extracted"),
                        notes=param_data.get("notes", ""),
                    )
                    db.add(param)
                    param_imported += 1

        db.commit()
        print(f"Done: {tech_imported} tech_nodes, {art_imported} artifacts, {param_imported} parameters")
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
    sys.exit(run())
