from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.services.data_loader import load_json

router = APIRouter(tags=["domains"], dependencies=[Depends(get_current_user)])


def _build_tree(domains: list[dict]) -> list[dict]:
    nodes = {d["id"]: {**d, "children": []} for d in domains}
    roots: list[dict] = []

    for domain in nodes.values():
        parent_id = domain.get("parent_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(domain)
        else:
            roots.append(domain)

    def sort_key(item: dict) -> tuple:
        return (item.get("sort_order", 0), item.get("name", ""))

    def sort_children(items: list[dict]) -> None:
        items.sort(key=sort_key)
        for item in items:
            sort_children(item["children"])

    sort_children(roots)
    return roots


@router.get("/domains/tree")
def get_domains_tree() -> list[dict]:
    try:
        domains = load_json("domains.json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="domains.json not found") from exc

    if not isinstance(domains, list):
        raise HTTPException(status_code=500, detail="domains.json is invalid")

    return _build_tree(domains)
