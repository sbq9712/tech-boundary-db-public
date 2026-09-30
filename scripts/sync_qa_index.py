#!/usr/bin/env python3
"""管线 → canonical-qa 增量索引同步（一/四节 Step10 收口）。

背景：本地管线发布到 breadth/data 的记录会进入 web 展示与每日 feed 包，
但主仓库门户问答（canonical-qa）的索引资产是镜像打包的 lite 快照，
新发布的记录不在索引中 → 问答检索不到新情报。

本脚本：
  1. 计算 管线发布视图 与上次同步基线的键级差异
     （键 = json.dumps([t,d,u])，与 feed 稳定键同构；含 | 的标题安全）；
  2. 把新增记录作为单个增量文档（一条记录一个 chunk，chunk 级携带
     标题/日期/来源/链接，保证引用卡可溯源）POST /api/index/upsert；
  3. 成功后落盘 runtime/qa-index-sync/state.json，幂等：无差异即秒级退出。

同步范围（实测约束下的设计决策，2026-09-29）：
  - 只推送「基线中不存在的键」（新记录）。已存在记录的内容更新不重推：
    实测 66,858 个共同键中仅 1 个正文变化，且增量嵌入必须截断正文
    （MAX_CHUNK_CHARS），重推会以弱索引覆盖基础索引的全文版本。
    完整的历史重建走离线基础索引重建（一节「从源头完整重建」）。
  - 性能实测（12 核 CPU bge-m3）：嵌入 ~1.9s/条（500 字符），
    8.4k 新记录 ≈ 5 小时，分批断点可跨多次定时运行续传。

首次基线 = runtime/qa-index-sync/base-lite.json（容器镜像内烘焙 lite
的快照，docker cp 提取——这是基础索引的真实内容源）；不存在时回退
services/canonical-qa/data/processed/all-records-lite.json；再不存在
则以空集为基线（全量同步，先用 --dry-run 确认规模）。

用法：
  python3 scripts/sync_qa_index.py                 # 增量同步
  python3 scripts/sync_qa_index.py --dry-run       # 只算差异不推送
  python3 scripts/sync_qa_index.py --qa-url URL    # 覆盖服务地址
  python3 scripts/sync_qa_index.py --reset-baseline  # 以当前发布视图重置基线
环境变量：TECHDB_QA_SYNC_URL（默认 http://127.0.0.1:8767）、
TECHDB_QA_INDEX_TOKEN（/api/index/upsert 鉴权）。
"""
from __future__ import annotations

import argparse
import fcntl
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
BASE_LITE = SYNC_DIR / "base-lite.json"  # 容器镜像内烘焙 lite 的快照（基础索引的真实内容源）
LOCK_PATH = SYNC_DIR / "sync.lock"

BATCH_RECORDS = 1000         # 单次 upsert 的记录数：实测 ~1.9s/条（500 字符嵌入）≈ 32 分钟/批 < 40 分钟超时
MAX_CHUNK_CHARS = 500        # 单 chunk 正文截断（摘要在前；实测 CPU 嵌入 8192 token 不可行）
UPSERT_TIMEOUT = 2400  # 单批嵌入+BM25 重建预算（40 分钟）


def stable_record_id(rec: dict) -> str:
    """与 scripts/rebuild_qa_base_index.py 同源的确定性 uuid5 身份。

    URL 稳定则 ID 稳定（无 URL 记录用 t|d|a 派生）——统一身份键：
    管线增量 chunk、离线基础索引、（未来）导入链都以它对齐同一记录。"""
    import uuid
    url = str(rec.get("u", "") or "").strip()
    identity = f"url:{url}" if url else (
        f"tda:{rec.get('t', '')}|{rec.get('d', '')}|{rec.get('a', '')}")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


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
    """上次同步基线的 {key_hash: record_digest}。

    首次基线优先 base-lite.json（容器镜像内烘焙 lite 的快照——基础索引的
    真实内容源；主机侧 IMAGE_LITE 可能比镜像新，用它会把已检索不到的
    旧记录误判为已入索引）。
    """
    state = load_state()
    if state.get("key_hashes"):
        return dict(state["key_hashes"])
    if BASE_LITE.exists():
        log("无 state.json —— 以 base-lite.json（容器烘焙快照）为首次基线")
        records = json.loads(BASE_LITE.read_text("utf-8"))
        return {key_digest(record_key(r)): record_digest(r) for r in records}
    if IMAGE_LITE.exists():
        log("base-lite 快照缺失 —— 回退镜像打包 lite 为首次基线")
        records = json.loads(IMAGE_LITE.read_text("utf-8"))
        return {key_digest(record_key(r)): record_digest(r) for r in records}
    log("基线快照不存在 —— 以空集为基线（全量同步，建议先 --dry-run）")
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
                # 统一身份（2026-09-30）：与基础索引重建同源的 uuid5
                # （URL 稳定则 ID 稳定）→ server 端 dedup/版本替换以同一
                # 身份对齐增量 chunk 与基础记录，跨基线不再重复召回。
                "record_id": stable_record_id(rec),
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


RECORD_OPS_TIMEOUT = 120  # record 变更只做内存过滤+墓碑落盘，预算远小于嵌入


def post_record_ops(ops: list[tuple[str, dict]], qa_url: str, token: str) -> dict:
    """把 record 级 UPDATE/DELETE 提交给服务端。

    服务端职责（/api/index/record-mutate，2026-09-30 新增）：
      - update：删除该 record_key_sha 的既有增量 chunk，并对基础索引中的
        同键记录做「新版本替换」遮蔽（推送侧随后以普通 ADD 批次上送新版本）
      - delete：删除增量 chunk，并把 record_key_sha 写入持久化墓碑，
        向量/BM25/图谱/引用/会话证据全链路屏蔽
    """
    body = json.dumps({"ops": [{"record_key_sha": kh, **op} for kh, op in ops]},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{qa_url.rstrip('/')}/api/index/record-mutate", data=body, method="POST",
        headers={"Content-Type": "application/json", **({"X-TechDB-Index-Token": token} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=RECORD_OPS_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="管线 → canonical-qa 索引同步")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qa-url", default=os.getenv("TECHDB_QA_SYNC_URL", "http://127.0.0.1:8767"))
    parser.add_argument("--reset-baseline", action="store_true",
                        help="以当前管线 lite 重置基线（不推送）")
    args = parser.parse_args(argv)

    # 防并发：4 小时定时器与手动运行/上一次未完成的批次重叠时直接让路
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    lock_handle = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("另一个同步进程正在运行 —— 本次退出")
        lock_handle.close()
        return 0

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
    if (not args.reset_baseline and state.get("data_version") == data_version
            and not state.get("pending_record_ops")):
        # 幂等退出；但有待重试的 record 变更时必须继续——服务端镜像升级后
        # （2026-09-30 实测：404 → 端点可用）靠这一轮把欠账补上并推进基线
        log("data_version 未变化 —— 已是最新，退出（幂等）")
        return 0

    baseline = {} if args.reset_baseline else baseline_key_hashes()
    log(f"基线条目：{len(baseline)}")
    # ── 全量差异：ADD / UPDATE / DELETE（2026-09-30 修复：旧实现只认新增、
    # 忽略内容更新、不处理删除，却照样推进基线 → 源修订/删除永远进不了问答
    # 索引，且基线声明与索引实际内容脱节）──
    fresh: dict[str, dict] = {}
    changed: dict[str, dict] = {}
    for rec in records:
        kh = key_digest(record_key(rec))
        rd = record_digest(rec)
        prev = baseline.get(kh)
        if prev is None:
            fresh[kh] = rec
        elif prev != rd:
            changed[kh] = rec
    published_keys = {key_digest(record_key(r)) for r in records}
    deleted_keys = [kh for kh in baseline if kh not in published_keys]
    if not args.reset_baseline:
        log(f"差异：新增 {len(fresh)} / 内容更新 {len(changed)} / 删除 {len(deleted_keys)}")
        for kh in deleted_keys[:5]:
            log(f"  [del] {kh[:12]}…")
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
    if not fresh and not changed and not deleted_keys:
        log("发布视图与基线一致 —— 无需变更（只读退出，不落 state）")
        return 0

    # ── dry-run：严格只读（2026-09-30 修复：旧实现 no-new 分支在本检查
    # 之前就写 state，--dry-run 会推进基线）──
    if args.dry_run:
        log(f"[dry-run] 目标 {args.qa_url}：ADD {len(fresh)} / UPDATE {len(changed)} "
            f"/ DELETE {len(deleted_keys)}；不落任何 state")
        for kh, rec in list(fresh.items())[:3]:
            log(f"  [add] {str(rec.get('t', ''))[:40]}")
        return 0

    state_partial = load_state()
    pushed_doc_ids = set(state_partial.get("pushed_doc_ids") or [])
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    if not token:
        token_file = SYNC_DIR / "token"  # chmod 600，不入 git（runtime/）
        if token_file.exists():
            token = token_file.read_text("utf-8").strip()

    # ── record 级变更（UPDATE/DELETE）走 /api/index/record-mutate（服务端
    # 删除旧 chunk + 对基础版本做替换遮蔽/删除墓碑，检索侧全链路生效）。
    # 服务端不支持（404）或失败时：变更记入 pending_record_ops 且【不推进
    # 这些键的基线】——宁可下轮重做，不可把未生效的更新/删除谎报为已同步。
    # ADD 批次推送契约不变（document 整体替换语义，幂等）。──
    pending_ops = state_partial.get("pending_record_ops") or {}
    record_ops: dict[str, dict] = {}
    for kh in changed:
        record_ops[kh] = {"op": "update"}
    for kh in deleted_keys:
        record_ops[kh] = {"op": "delete"}
    for kh, op in pending_ops.items():
        record_ops.setdefault(kh, op)
    if record_ops:
        t0 = time.time()
        try:
            result = post_record_ops(sorted(record_ops.items()), args.qa_url, token)
            log(f"record 变更：update {len(changed)} + delete {len(deleted_keys)} + "
                f"pending {len(pending_ops)} → ok={result.get('updated')}（{time.time() - t0:.1f}s）")
            record_ops_ok = True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                log("[WARN] 服务端不支持 /api/index/record-mutate（镜像未升级）——"
                    "变更保留在 pending_record_ops，这些键的基线不推进")
            else:
                log(f"[ERROR] record-mutate HTTP {exc.code}：{exc.read()[:200]}")
            record_ops_ok = False
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log(f"[ERROR] record-mutate 失败：{exc}")
            record_ops_ok = False
    else:
        record_ops_ok = True

    items = list(fresh.items())
    # 内容更新的记录在 record-mutate 成功后必须随 ADD 批次上送新版本——
    # 服务端 update 只删旧增量 chunk + 遮蔽基础旧版本；新版本不随批上送
    # 的话该记录会从索引彻底消失（旧被遮、新未至，2026-09-30 端到端实测
    # 发现）。record 变更失败（record_ops_ok=False）时不上送：服务端未
    # 删旧版本，重推会以弱索引覆盖基础索引全文版本（见模块头注释）。
    if record_ops_ok:
        items += list(changed.items())
    total_batches = (len(items) + BATCH_RECORDS - 1) // BATCH_RECORDS
    synced = 0
    for batch_no in range(total_batches):
        doc_id = f"pipeline-lite-{data_version[:12]}-{batch_no}"
        if doc_id in pushed_doc_ids:
            log(f"批次 {batch_no} 此前已成功（{doc_id}）——跳过")
            synced += min(BATCH_RECORDS, len(items) - batch_no * BATCH_RECORDS)
            continue
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
        log(f"批次 {batch_no}/{total_batches - 1}：{len(batch)} 条 → {result.get('status')}（{time.time() - t0:.1f}s）")
        synced += len(batch)
        # 每批成功即推进断点（下轮重跑只推缺失批）
        state_partial.setdefault("pushed_doc_ids", []).append(doc_id)
        state_partial["partial_at"] = datetime.now(timezone.utc).isoformat()
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state_partial, ensure_ascii=False), "utf-8")

    # ── 基线推进：ADD 批次全部成功；record 变更成功 → 完整基线；
    # record 变更未成功 → 这些键按操作前基线回填并留在 pending_record_ops
    # （update：保留旧 digest；delete：键回填旧 digest），下轮重试。──
    new_key_hashes = {key_digest(record_key(r)): record_digest(r) for r in records}
    if not record_ops_ok:
        for kh in record_ops:
            if kh in baseline:
                new_key_hashes[kh] = baseline[kh]
    final_state = {
        "data_version": data_version,
        "key_hashes": new_key_hashes,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "records": len(records),
        "last_pushed": synced,
        "pushed_doc_ids": [],
    }
    if not record_ops_ok:
        final_state["pending_record_ops"] = record_ops
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(final_state, ensure_ascii=False), "utf-8")
    if not record_ops_ok:
        log(f"同步部分完成：ADD {synced} 条入索引；{len(record_ops)} 条 update/delete "
            f"待服务端支持后重试；状态已落盘 {STATE_PATH}")
        return 3
    log(f"同步完成：ADD {synced} / UPDATE+DELETE {len(record_ops)} 条；状态已落盘 {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
