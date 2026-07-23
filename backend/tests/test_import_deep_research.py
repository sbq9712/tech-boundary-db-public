from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for candidate in [PROJECT_ROOT / "backend" / "scripts", PROJECT_ROOT / "scripts", Path("/app/scripts")]:
    if candidate.exists():
        sys.path.insert(0, str(candidate))
        break

import import_deep_research


def test_discover_kb_documents_reads_frontmatter_and_skips_spec(tmp_path):
    kb = tmp_path / "knowledge-base"
    track = kb / "AIDC全产业链"
    track.mkdir(parents=True)
    (kb / "_知识库文档规范.md").write_text("---\ntitle: 规范\ntaxonomy_leaf: 示例\n---\n", encoding="utf-8")
    doc = track / "AIDC全产业链_供电与互连技术边界.md"
    doc.write_text(
        "---\n"
        "title: AIDC全产业链_供电与互连技术边界\n"
        "taxonomy_leaf: AI与智能科技/AI硬件层/算力能源基础设施\n"
        "status: active\n"
        "version: 1.0\n"
        "---\n"
        "## §2 关键指标清单与边界\n"
        "| 指标 | 当前最佳值 | 边界（理论/工程极限） | 测试条件 | 来源 | 可信度 | 备注 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 800VDC 架构 | 云厂导入 | 工程认证 | AIDC 机柜 | 国金证券 | ⚠ | 高压直流升级 |\n",
        encoding="utf-8",
    )

    docs = import_deep_research.discover_kb_documents(kb)

    assert [d.title for d in docs] == ["AIDC全产业链_供电与互连技术边界"]
    assert docs[0].vault_path == "AIDC全产业链/AIDC全产业链_供电与互连技术边界.md"
    assert docs[0].taxonomy_leaf == "AI与智能科技/AI硬件层/算力能源基础设施"
    assert docs[0].parameters[0]["parameter_name"] == "800VDC 架构"
    assert docs[0].parameters[0]["value_text"] == "云厂导入"


def test_stable_ids_are_deterministic_from_vault_path():
    assert import_deep_research.stable_artifact_id("A/B_技术边界.md") == import_deep_research.stable_artifact_id("A/B_技术边界.md")
    assert import_deep_research.stable_tech_node_id("AI与智能科技/AI硬件层/芯片") == import_deep_research.stable_tech_node_id("AI与智能科技/AI硬件层/芯片")
    assert import_deep_research.stable_artifact_id("SOC/SOFC行业深度报告.md") == "ART-20260712-4F444B2861"


def test_parse_parameters_understands_three_value_research_metrics():
    text = (
        "## §2 关键技术指标\n"
        "| 关键指标 | 理论值/物理边界 | 场景需求值 | 实际值/公开披露 | 条件/口径 | 数据状态 | 进一步调研方向 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 系统负荷跟踪 | 无统一单值 | 秒级 | 缺MW级整站数据 | 整站口径 | ❓ 数据缺口 | 获取高频实测曲线 |\n"
    )

    parameters = import_deep_research._parse_parameters(text)

    assert parameters[0]["value_text"] == "缺MW级整站数据"
    assert parameters[0]["condition_text"] == "整站口径"
    assert parameters[0]["verification_status"] == "disputed"
    assert parameters[0]["notes"] == "获取高频实测曲线"


def test_parameter_type_does_not_treat_technical_scale_as_market_size():
    assert import_deep_research._parameter_type("系统净电效率") == "technical"
    assert import_deep_research._parameter_type("全球市场规模") == "economic"
