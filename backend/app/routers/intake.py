from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user

router = APIRouter(
    tags=["intake"],
    dependencies=[Depends(get_current_user)],
)

INTAKE_CHANNELS = [
    {
        "id": "server_fetch",
        "name": "从服务器获取信息",
        "status": "placeholder",
        "description": "为后续从内部服务器、共享目录或数据服务拉取材料预留入口。",
        "expected_inputs": ["source_path", "source_type", "submitted_by", "confidentiality"],
        "next_step": "定义服务器侧数据源清单和读取权限。",
    },
    {
        "id": "crawler_fetch",
        "name": "自动化扒取信息",
        "status": "placeholder",
        "description": "为后续网页、付费数据库、浏览器自动化或 crawler 接入预留入口。",
        "expected_inputs": ["source_url", "source_type", "crawl_profile", "snapshot_required"],
        "next_step": "先确认合规边界，再接入具体采集器。",
    },
    {
        "id": "direct_upload",
        "name": "直接上传信息",
        "status": "available_via_existing_pages",
        "description": "当前可通过上传复核页、批量导入页进入草稿层；本接口描述未来统一 intake schema。",
        "expected_inputs": ["title", "original_text", "attachments", "technology_candidates", "industry_candidates"],
        "next_step": "将现有上传/批量导入逐步映射到统一 intake schema。",
    },
]

INTAKE_SCHEMA = {
    "object": "intake_item",
    "version": "0.1-placeholder",
    "required_fields": [
        "channel",
        "title",
        "source_type",
        "submitted_by",
        "submitted_at",
        "confidentiality",
        "review_status",
    ],
    "optional_fields": [
        "source_url",
        "source_path",
        "original_text",
        "summary",
        "event_time",
        "actor_or_company",
        "technology_node_candidates",
        "industry_node_candidates",
        "parameter_candidates",
        "attachments",
        "snapshot_path",
        "initial_reliability",
        "review_need",
    ],
    "review_statuses": ["draft", "pending_review", "human_checked", "rejected"],
    "confidentiality_levels": ["公开", "内部", "非公开", "付费来源", "受限来源"],
}


@router.get("/intake/status")
def get_intake_status() -> dict:
    return {
        "status": "placeholder_ready",
        "message": "第一阶段仅定义信息进入系统的接口边界，暂不实现完整自动采集。",
        "channels": INTAKE_CHANNELS,
        "non_goals": [
            "不在本阶段实现完整 crawler",
            "不自动确认技术边界更新",
            "不绕过人工审核写入 confirmed alert",
        ],
    }


@router.get("/intake/schema")
def get_intake_schema() -> dict:
    return {
        "status": "placeholder_ready",
        "schema": INTAKE_SCHEMA,
        "channels": INTAKE_CHANNELS,
    }


@router.get("/sources")
def get_sources_overview() -> dict:
    return {
        "status": "placeholder_ready",
        "message": "信息源页面第一阶段展示来源类型和接入状态；真实 source/evidence 表后续再建。",
        "source_types": [
            "人工录入",
            "CSV/Excel 批量导入",
            "内部服务器文件",
            "公开网页",
            "付费数据库摘录",
            "论文/专利/PDF",
            "同事整理材料",
        ],
        "current_available_paths": [
            "upload_review.html",
            "excel_import.html",
        ],
        "future_capabilities": INTAKE_CHANNELS,
    }
