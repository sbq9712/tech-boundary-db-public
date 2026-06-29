from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user

router = APIRouter(tags=["dashboards"], dependencies=[Depends(get_current_user)])

_DASHBOARDS = [
    {
        "id": "sofc-soc",
        "name": "SOFC / SOC",
        "scope": "数据中心电源、分布式发电、rSOC",
        "metrics": ["电解质电导率", "堆寿命", "系统效率", "单位投资成本", "燃料利用率"],
        "status": "重点研究",
        "query": "SOFC",
        "domain": "SOFC",
    },
    {
        "id": "aidc-power",
        "name": "AIDC 能源系统",
        "scope": "供电架构、备用电源、热管理",
        "metrics": ["可用率", "PUE", "电力容量", "审批周期", "备用时长"],
        "status": "进行中",
        "query": "AIDC",
        "domain": "AIDC",
    },
    {
        "id": "long-duration-storage",
        "name": "长时储能",
        "scope": "液流、压缩空气、热储能、氢储能",
        "metrics": ["LCOS", "储能时长", "循环寿命", "地理约束", "响应时间"],
        "status": "观察",
        "query": "长时储能",
        "domain": "储能",
    },
]


@router.get("/dashboards")
def list_dashboards(q: str | None = Query(default=None, max_length=100)) -> dict:
    keyword = (q or "").strip().lower()
    items = _DASHBOARDS
    if keyword:
        items = [
            item for item in _DASHBOARDS
            if keyword in item["name"].lower()
            or keyword in item["scope"].lower()
            or any(keyword in metric.lower() for metric in item["metrics"])
        ]
    return {"items": items, "total": len(items)}
