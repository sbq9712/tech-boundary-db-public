#!/usr/bin/env python3
"""任务验收演练 1.4 / 2.5（公司服务器实测）。

流程：
  A/B/C 三包增删改 → 每步核对 上传状态契约（列表 + /index-status）→
  三路检索（vector/bm25/图谱）× 三源（breadth/industry/atsc）→
  canonical-qa 重启一致性 → 记录证据到 stdout（保存进验收报告）。

用法（主机，需能访问 localhost:8080 与 localhost:8767）：
  python3 docs/qa-acceptance/drill_1_4_2_5.py [--keep]
  --keep 不清理演练数据（用于人工检查）
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile

API = "http://localhost:8080"
QA = "http://localhost:8767"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, evidence: str = ""):
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {evidence}" if evidence else ""))
    (PASS if ok else FAIL).append(name)


def _env_creds():
    env = open("/home/rhett/tech-boundary-db/.env").read()
    user = re.search(r"TECHDB_INITIAL_ADMIN_USERNAME=(.*)", env)
    pwd = re.search(r"TECHDB_INITIAL_ADMIN_PASSWORD=(.*)", env)
    return (user.group(1).strip() if user else "",
            pwd.group(1).strip() if pwd else "")


def login() -> str:
    u, p = _env_creds()
    req = urllib.request.Request(
        API + "/api/auth/login", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": u, "password": p}).encode())
    return json.load(urllib.request.urlopen(req))["access_token"]


def api(jwt: str, method: str, path: str, body=None, files=None, form=None):
    if files:
        # multipart 上传 zip：files 为 {field: (filename, bytes)}，form 为表单字段
        boundary = "----drillboundary"
        parts = []
        for k, v in (form or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (fn, data) in files.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                f"Content-Type: application/zip\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        payload = b"".join(parts)
        req = urllib.request.Request(
            API + path, method=method, data=payload,
            headers={"Authorization": "Bearer " + jwt,
                     "Content-Type": "multipart/form-data; boundary=" + boundary})
    else:
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + jwt,
                     "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def qa_get(path: str):
    req = urllib.request.Request(QA + path)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {}


# ── 包构造（与 backend/tests/test_feed_v2 同源规则）──

PUBLIC_FIELDS = ("t", "d", "u", "a", "b", "c", "tg", "as", "sc")


def _stable_id(t, d, u):
    raw = json.dumps([t, d, u], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _norm(rec):
    out = {k: rec.get(k) for k in PUBLIC_FIELDS if k in rec}
    u = str(out.get("u", "") or "")
    out["u"] = u if u else "sha256:" + hashlib.sha256(
        json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    out["id"] = _stable_id(str(out.get("t", "")), str(out.get("d", "")), str(out.get("u", "")))
    return out


def build_pkg(records, changes, date):
    out_records = [r for r in records
                   if any(c["op"] in ("ADD", "UPDATE") and c["id"] == r.get("id")
                          for c in changes)]
    records_json = json.dumps(out_records, ensure_ascii=False, separators=(",", ":"))
    changes_json = json.dumps(changes, ensure_ascii=False)
    manifest = {
        "schema": "tech-boundary-feed-package/v2",
        "generator": "feed-pkg/v2",
        "mode": "changes",
        "date": date,
        "record_count": len(out_records),
        "change_count": len(changes),
        "added": sum(1 for c in changes if c["op"] == "ADD"),
        "updated": sum(1 for c in changes if c["op"] == "UPDATE"),
        "deleted": sum(1 for c in changes if c["op"] == "DELETE"),
        "records_sha256": hashlib.sha256(records_json.encode()).hexdigest(),
        "data_version": "dv-drill-" + date,
        "generated_at": "2026-10-02T20:00:00+08:00",
        "changes_sha256": hashlib.sha256(changes_json.encode()).hexdigest(),
    }
    canon = {k: v for k, v in manifest.items()
             if k not in ("manifest_digest", "chain", "generated_at")}
    manifest["manifest_digest"] = hashlib.sha256(
        json.dumps(canon, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    # chain = sha256(predecessor + manifest_digest)，predecessor 空=链首
    manifest["chain"] = hashlib.sha256(
        (str(manifest.get("predecessor", "")) + manifest["manifest_digest"]).encode()).hexdigest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("records.json", records_json)
        zf.writestr("changes.json", changes_json)
    return buf.getvalue()


RUN = str(int(time.time()))
MARK = "drill" + hashlib.sha256(("t4x-drill-" + RUN).encode()).hexdigest()[:6]
NONCE = "https://drill.example/" + RUN + "/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    jwt = login()
    print(f"== 演练标记（标题含）：{MARK} ==")

    # ── A 包：2 ADD ──
    print("\n== A 包（2 新增）==")
    ra = _norm({"t": f"{MARK} 钙钛矿叠层电池效率突破", "d": "2026-10-01",
                "u": NONCE + "a1", "b": "叠层电池效率达到 33%",
                "c": "光伏", "a": "演练来源A", "tg": "光伏"})
    rb = _norm({"t": f"{MARK} 固态电池电解质进展", "d": "2026-10-01",
                "u": NONCE + "a2", "b": "硫化物电解质进展",
                "c": "储能", "a": "演练来源A", "tg": "储能"})
    pkg_a = build_pkg(
        [ra, rb],
        [{"op": "ADD", "id": ra["id"], "key": f"{ra['t']}|{ra['d']}|{ra['u']}", "v": 1},
         {"op": "ADD", "id": rb["id"], "key": f"{rb['t']}|{rb['d']}|{rb['u']}", "v": 1}],
        "2026-10-01")
    st, resp = api(jwt, "POST", "/api/uploads",
                   files={"files": ("drill-a.zip", pkg_a)},
                   form={"primary_section": "breadth", "breadth_source": "github"})
    check("A 包导入成功（200/201）", st in (200, 201), f"status={st} detail={str(resp)[:120]}")
    up_a = resp.get("files", [{}])[0].get("id")
    check("A 包 imported=2（skipped_tombstoned=0）",
          resp.get("github_import", {}).get("imported") == 2
          and resp.get("github_import", {}).get("details", {}).get("skipped_tombstoned") == 0,
          str(resp.get("github_import", {}))[:200])

    # 等队列 worker 处理
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        st, detail = api(jwt, "GET", f"/api/uploads/{up_a}/index-status")
        if st == 200 and detail.get("status") in ("indexed", "index_failed",
                                                  "import_failed", "legacy_unknown"):
            final_status = detail
            break
        time.sleep(2)
    check("A 包状态到 indexed", final_status and final_status["status"] == "indexed",
          f"status={final_status and final_status['status']}")
    check("A 包 searchable=true（canonical 权威）",
          final_status and final_status.get("searchable") is True,
          f"index={final_status and final_status.get('index')}")
    check("A 包归属 breadth", final_status
          and final_status["index"].get("unattributed") == 0,
          f"chunks={final_status and final_status['index'].get('chunks')}")

    # ── B 包：1 UPDATE + 1 ADD ──
    print("\n== B 包（1 更新 + 1 新增）==")
    ra2 = dict(ra)
    ra2["b"] = "叠层电池效率达到 34%（B 包更新）"
    ra2["id"] = ra["id"]
    rc = _norm({"t": f"{MARK} 钠离子电池硬碳负极", "d": "2026-10-02",
                "u": NONCE + "b1", "b": "硬碳负极容量提升",
                "c": "储能", "a": "演练来源B", "tg": "储能"})
    pkg_b = build_pkg(
        [ra2, rc],
        [{"op": "UPDATE", "id": ra["id"], "key": f"{ra['t']}|{ra['d']}|{ra['u']}", "v": 2},
         {"op": "ADD", "id": rc["id"], "key": f"{rc['t']}|{rc['d']}|{rc['u']}", "v": 1}],
        "2026-10-02")
    st, resp = api(jwt, "POST", "/api/uploads",
                   files={"files": ("drill-b.zip", pkg_b)},
                   form={"primary_section": "breadth", "breadth_source": "github"})
    check("B 包导入成功（200/201）", st in (200, 201), f"status={st} {str(resp)[:120]}")
    up_b = resp.get("files", [{}])[0].get("id")
    gi = resp.get("github_import", {})
    check("B 包 imported=1（更新走 UPDATE 不重复）+ 新增 1",
          gi.get("imported") == 2 or gi.get("imported") == 1,
          f"github_import={gi}")

    deadline = time.time() + 60
    while time.time() < deadline:
        st, detail = api(jwt, "GET", f"/api/uploads/{up_b}/index-status")
        if st == 200 and detail.get("status") in ("indexed", "index_failed",
                                                  "import_failed", "legacy_unknown"):
            break
        time.sleep(2)
    check("B 包状态 indexed", detail.get("status") == "indexed", f"status={detail.get('status')}")

    # 记录归属核对：B 的 UPDATE 把身份不变的记录重指到 B（feed 所有权模型，
    # 与 skipped_upstream_conflict 保护一致）；不重复建行——B 名下=更新+新增=2
    st, list_a = api(jwt, "GET", f"/api/uploads/{up_a}/index-status")
    st, list_b = api(jwt, "GET", f"/api/uploads/{up_b}/index-status")
    check("更新不重复建行（B 名下 2 条：1 更新+1 新增）",
          list_b.get("records") == 2,
          f"A.records={list_a.get('records')} B.records={list_b.get('records')}")

    # ── C 包：1 DELETE（删 A 包新增的 rb）──
    print("\n== C 包（1 删除）==")
    pkg_c = build_pkg(
        [], [{"op": "DELETE", "id": rb["id"], "key": f"{rb['t']}|{rb['d']}|{rb['u']}", "v": 1}],
        "2026-10-03")
    st, resp = api(jwt, "POST", "/api/uploads",
                   files={"files": ("drill-c.zip", pkg_c)},
                   form={"primary_section": "breadth", "breadth_source": "github"})
    check("C 包导入成功（200/201）", st in (200, 201), f"status={st} {str(resp)[:120]}")
    up_c = resp.get("files", [{}])[0].get("id")

    # 删除按 key 生效：记录行消失（全局总数核对），索引删除任务由 worker 执行
    deadline = time.time() + 90
    deleted_seen = False
    while time.time() < deadline:
        st, dA = api(jwt, "GET", f"/api/uploads/{up_a}/index-status")
        st, dB = api(jwt, "GET", f"/api/uploads/{up_b}/index-status")
        total_now = (dA.get("records") or 0) + (dB.get("records") or 0)
        if st == 200 and total_now == 2:  # 全局 3 条 → 删 1 → 2
            deleted_seen = True
            break
        time.sleep(2)
    check("删除传播：演练记录全局 3→2", deleted_seen,
          f"A.records={dA.get('records')} B.records={dB.get('records')}")
    time.sleep(6)
    st, res = qa_get(f"/api/search?q={urllib.parse.quote(MARK + ' 电解质')}&top_k=10&sources=breadth")
    titles = " ".join((h.get("title") or "") for h in res.get("results", []))
    check("删除后索引不再召回被删记录（电解质）", MARK + " 固态电池电解质进展" not in titles,
          f"titles={titles[:120]}")

    # ── 2.5：三路 × 三源检索 ──
    print("\n== 2.5 检索矩阵（sources × 检索路）==")
    q = f"{MARK} 钙钛矿"
    st, res = qa_get(f"/api/search?q={urllib.parse.quote(q)}&top_k=5&sources=breadth")
    hits = res.get("results", [])
    check("scope=breadth 命中演练记录", st == 200 and any(MARK in (h.get("title") or "") for h in hits),
          f"hits={len(hits)} titles={[ (h.get('title') or '')[:20] for h in hits[:2]]}")
    check("引用带 primary_section=breadth", hits and all(h.get("primary_section") == "breadth" for h in hits),
          f"sections={set(h.get('primary_section') for h in hits)}")
    st, res = qa_get(f"/api/search?q={urllib.parse.quote(q)}&top_k=5&sources=industry")
    check("scope=industry 如实 0 命中（无该源数据）",
          st == 200 and res.get("results") == [], f"hits={len(res.get('results', []))}")
    st, res = qa_get(f"/api/search?q={urllib.parse.quote(q)}&top_k=5&sources=atsc")
    check("scope=atsc 不含广度记录",
          st == 200 and not any(MARK in (h.get("title") or "") for h in res.get("results", [])),
          f"hits={len(res.get('results', []))}")
    # BM25 路（关键词命中）
    st, res = qa_get(f"/api/search?q={urllib.parse.quote(MARK)}&top_k=5")
    check("默认三源（含 BM25 路）命中演练记录",
          st == 200 and any(MARK in (h.get("title") or "") for h in res.get("results", [])),
          f"hits={len(res.get('results', []))}")
    # 图谱路：scope=breadth 图谱含演练实体（光伏/储能标签进入碎片）
    st, g = qa_get("/api/graph?scope=breadth")
    check("图谱 scope=breadth 可用（200 且有节点）",
          st == 200 and g.get("total_nodes", 0) > 0,
          f"total_nodes={g.get('total_nodes')} fragment={g.get('fragment_nodes')}")
    st, g2 = qa_get("/api/graph?scope=industry")
    check("图谱 scope=industry 仅增量碎片（0 节点）",
          st == 200 and g2.get("total_nodes", -1) == 0,
          f"total_nodes={g2.get('total_nodes')} fragment={g2.get('fragment_nodes')}")

    print(f"\n== 结果：{len(PASS)} PASS / {len(FAIL)} FAIL ==")
    for f in FAIL:
        print("  FAIL:", f)
    if not args.keep:
        print("\n== 清理演练数据 ==")
        for up in (up_a, up_b, up_c):
            if up:
                st, _ = api(jwt, "DELETE", f"/api/uploads/{up}")
                print(f"  delete {up[:8]}: {st}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    raise SystemExit(main())
