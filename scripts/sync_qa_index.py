#!/usr/bin/env python3
"""管线 → canonical-qa 增量索引同步（一/四节 Step10 收口）。

背景：本地管线发布到 breadth/data 的记录会进入 web 展示与每日 feed 包，
但主仓库门户问答（canonical-qa）的索引资产是镜像打包的 lite 快照，
新发布的记录不在索引中 → 问答检索不到新情报。

本脚本：
  1. 计算 管线 all-records-lite.json 与上次同步基线的键级差异
     （键 = json.dumps([t,d,u])，与 feed 稳定键同构；含 | 的标题安全）；
  2. 把新增记录作为单个增量文档（一条记录一个 chunk，chunk 级携带
     标题/日期/来源/链接，保证引用卡可溯源）POST /api/index/upsert；
  3. 成功后落盘 runtime/qa-index-sync/state.json（键哈希集 +
     data_version），幂等：无差异或 data_version 未变即秒级退出。

首次运行以 services/canonical-qa/data/processed/all-records-lite.json
（镜像打包内容）为基线，此后以 state.json 的键哈希集为基线。

用法：
  python3 scripts/sync_qa_index.py                 # 增量同步
  python3 scripts/sync_qa_index.py --dry-run       # 只算差异不推送
  python3 scripts/sync_qa_index.py --qa-url URL    # 覆盖服务地址
  python3 scripts/sync_qa_index.py --reset-baseline  # 以当前 lite 重置基线
环境变量：TECHDB_QA_SYNC_URL（默认 http://127.0.0.1:8767）、
TECHDB_QA_INDEX_TOKEN（/api/index/upsert 鉴权）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINE_LITE = REPO / "pipeline" / "data" / "processed" / "all-records-lite.json"
# 发布视图（与 canonical-qa 镜像打包 lite 同源的富化记录）：
BREADTH_PROCESSED = REPO / "breadth" / "data" / "processed"
IMAGE_LITE = REPO / "services" / "canonical-qa" / "data" / "processed" / "all-records-lite.json"
STATE_PATH = REPO / "runtime" / "qa-index-sync" / "state.json"
SYNC_DIR = STATE_PATH.parent

BATCH_RECORDS = 20000        # 单次 upsert 的最大记录数（chunk 数）——摊薄 BM25 重建
MAX_CHUNK_CHARS = 2000       # 单 chunk 正文截断
UPSERT_TIMEOUT = 7200  # 大批量嵌入+BM25 重建可达小时级


def log(msg: str) -> None:
    print(f"[qa-sync {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def record_key(rec: dict) -> str:
    return json.dumps([str(rec.get("t", "")), str(rec.get("d", "")), str(rec.get("u", ""))],
                      ensure_ascii=False)


def record_digest(rec: dict) -> str:
    ks = sorted(k for k in rec if k != "idx")
    return hashlib.sha256(json.dumps({k: rec.get(k) for k in ks}, ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()


def key_digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text("utf-8"))
    return {}


def _js_array(path: Path) -> list:
    """解析 window.__X_PARTS__.push([...]) 分片为 JSON 数组。"""
    text = path.read_text("utf-8")
    return json.loads(text.split("push(", 1)[1].rsplit(")", 1)[0])


def load_published_records() -> tuple[list[dict], str]:
    """发布视图 = lite-part（正文）+ meta-part（评分/精选等富化字段）按行合并。

    与 canonical-qa 镜像打包 all-records-lite.json 同源（publish 层产物），
    字段形态与旧索引资产一致。
    """
    lite_rows: list[dict] = []
    for f in sorted(BREADTH_PROCESSED.glob("lite-part-*.js")):
        lite_rows.extend(_js_array(f))
    meta_rows: dict[str, dict] = {}
    for f in sorted(BREADTH_PROCESSED.glob("meta-part-*.js")):
        for rec in _js_array(f):
            meta_rows[record_key(rec)] = rec
    merged: list[dict] = []
    for row in lite_rows:
        rich = meta_rows.get(record_key(row))
        merged.append({**row, **rich} if rich else row)
    return merged, f"published:{len(merged)}"


def baseline_key_hashes() -> dict[str, str]:
    """上次同步基线的 {key_hash: record_digest}。"""
    state = load_state()
    if state.get("key_hashes"):
        return dict(state["key_hashes"])
    if IMAGE_LITE.exists():
        log("无 state.json —— 以镜像打包 lite 为首次基线")
        records = json.loads(IMAGE_LITE.read_text("utf-8"))
        return {key_digest(record_key(r)): record_digest(r) for r in records}
    log("镜像 lite 也不存在 —— 以空集为基线（全量同步）")
    return {}


def chunk_text(rec: dict) -> str:
    summary = str(rec.get("as", "") or "")
    body = str(rec.get("b", "") or rec.get("fb", "") or "")
    text = f"{summary}\n{body}".strip() or str(rec.get("t", ""))
    return text[:MAX_CHUNK_CHARS]


def build_payload(records: list[dict], data_version: str, batch_no: int) -> dict:
    chunks = []
    for i, rec in enumerate(records):
        tags = rec.get("tg", [])
        if isinstance(tags, str):
            tags = [tags]
        chunks.append({
            "chunk_id": f"rec-{batch_no}-{i}",
            "text": chunk_text(rec),
            "title": str(rec.get("t", "") or "未命名情报"),
            "record_date": str(rec.get("d", "") or ""),
            "source_name": str(rec.get("a", "") or rec.get("s", "") or "pipeline"),
            "url": str(rec.get("u", "") or ""),
            "primary_category": str(rec.get("c", "") or "未分类"),
            "tags": [str(t) for t in tags][:5],
            "summary": str(rec.get("as", "") or "")[:500],
            "metadata": {
                "url": str(rec.get("u", "") or ""),
                "document_date": str(rec.get("d", "") or ""),
                "source_name": str(rec.get("a", "") or rec.get("s", "") or "pipeline"),
                "source": "pipeline-sync",
                "score": rec.get("sc"),
                "record_key_sha": key_digest(record_key(rec)),
            },
        })
    return {
        "document_id": f"pipeline-lite-{data_version[:12]}-{batch_no}",
        "filename": f"pipeline-lite-{data_version[:12]}.json",
        "title": f"广度情报管线快照 {data_version[:12]}（{batch_no}）",
        "primary_category": "管线同步",
        "secondary_categories": ["pipeline-sync"],
        "confidentiality": "public",
        "source_type": "pipeline",
        "checksum_sha256": hashlib.sha256(
            json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunks": chunks,
    }


def post_upsert(payload: dict, qa_url: str, token: str) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{qa_url.rstrip('/')}/api/index/upsert", data=body, method="POST",
        headers={"Content-Type": "application/json", **({"X-TechDB-Index-Token": token} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=UPSERT_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="管线 → canonical-qa 索引同步")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qa-url", default=os.getenv("TECHDB_QA_SYNC_URL", "http://127.0.0.1:8767"))
    parser.add_argument("--reset-baseline", action="store_true",
                        help="以当前管线 lite 重置基线（不推送）")
    args = parser.parse_args(argv)

    records, source = load_published_records()
    if not records:
        log(f"发布视图为空（{BREADTH_PROCESSED} 无分片）—— 回退管线 lite")
        if not PIPELINE_LITE.exists():
            log(f"管线 lite 也不存在：{PIPELINE_LITE}")
            return 1
        records = json.loads(PIPELINE_LITE.read_text("utf-8"))
    log(f"来源：{source}（{BREADTH_PROCESSED.name if 'published' in source else PIPELINE_LITE.name}）")
    data_version = hashlib.sha256(
        json.dumps([record_digest(r) for r in records], ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    log(f"管线 lite：{len(records)} 条 / data_version={data_version}")

    state = load_state()
    if not args.reset_baseline and state.get("data_version") == data_version:
        log("data_version 未变化 —— 已是最新，退出（幂等）")
        return 0

    baseline = {} if args.reset_baseline else baseline_key_hashes()
    log(f"基线条目：{len(baseline)}")
    fresh: dict[str, dict] = {}
    changed = 0
    for rec in records:
        kh = key_digest(record_key(rec))
        rd = record_digest(rec)
        prev = baseline.get(kh)
        if prev is None:
            fresh[kh] = rec
        elif prev != rd:
            changed += 1
            fresh[kh] = rec  # 内容变化 → 重插（upsert 按 document_id 幂等替换，键哈希随内容更新）
    log(f"差异：新增/变化 {len(fresh)} 条（其中内容更新 {changed} 条）")
    if args.reset_baseline:
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({
            "data_version": data_version,
            "key_hashes": {key_digest(record_key(r)): record_digest(r) for r in records},
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "records": len(records), "reset": True,
        }, ensure_ascii=False), "utf-8")
        log(f"基线已重置：{STATE_PATH}")
        return 0
    if not fresh:
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({
            "data_version": data_version,
            "key_hashes": {key_digest(record_key(r)): record_digest(r) for r in records},
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "records": len(records),
        }, ensure_ascii=False), "utf-8")
        log("无新增记录 —— 状态已对齐，退出")
        return 0

    if args.dry_run:
        log(f"[dry-run] 将推送 {len(fresh)} 条 → {args.qa_url}")
        return 0

    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    if not token:
        token_file = SYNC_DIR / "token"  # chmod 600，不入 git（runtime/）
        if token_file.exists():
            token = token_file.read_text("utf-8").strip()
    items = list(fresh.items())
    synced = 0
    for batch_no in range(0, (len(items) + BATCH_RECORDS - 1) // BATCH_RECORDS):
        batch = [rec for _, rec in items[batch_no * BATCH_RECORDS:(batch_no + 1) * BATCH_RECORDS]]
        payload = build_payload(batch, data_version, batch_no)
        t0 = time.time()
        try:
            result = post_upsert(payload, args.qa_url, token)
        except urllib.error.HTTPError as exc:
            log(f"[ERROR] upsert 批次 {batch_no} HTTP {exc.code}：{exc.read()[:200]}")
            return 1
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log(f"[ERROR] upsert 批次 {batch_no} 失败：{exc}")
            return 1
        log(f"批次 {batch_no}：{len(batch)} 条 → {result.get('status')}（{time.time() - t0:.1f}s）")
        synced += len(batch)

    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "data_version": data_version,
        "key_hashes": {key_digest(record_key(r)): record_digest(r) for r in records},
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "records": len(records),
        "last_pushed": synced,
    }, ensure_ascii=False), "utf-8")
    log(f"同步完成：{synced} 条入索引；状态已落盘 {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
