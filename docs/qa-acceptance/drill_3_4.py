#!/usr/bin/env python3
"""任务验收演练 3.4（公司服务器实测）：「情报类型」全链路。

流程：预览（列映射识别 情报类型）→ 合法表导入（news/literature 混合）→
记录类型落库+导航透出 → 索引 chunk_metadata 带类型 → 非法类型整文件拒绝
（无部分入库）→ 修复脚本 dry-run（应报告新导入行为一致，无需修复）→ 清理。

只读端点无鉴权（T8 设计，Docker 内网边界）；写端点走 API JWT。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "http://localhost:8080"
CANONICAL = "http://localhost:8767"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, evidence: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" | {evidence}" if evidence else ""))
    (PASS if ok else FAIL).append(name)
    return ok


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


def api(jwt: str, method: str, path: str, raw: bytes | None = None,
        content_type: str = "application/json"):
    body = raw if raw is not None else json.dumps({}).encode() if method in ("POST", "PATCH") else None
    req = urllib.request.Request(
        API + path, method=method, data=body,
        headers={"Authorization": f"Bearer {jwt}"} | ({"Content-Type": content_type} if body else {}))
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    bnd = "----drill34boundary"
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, blob, ct) in files.items():
        parts.append(
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
            f"Content-Type: {ct}\r\n\r\n".encode() + blob + b"\r\n")
    parts.append(f"--{bnd}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={bnd}"


def xlsx_bytes(rows) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MARK = "t34" + str(int(time.time()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    jwt = login()
    print(f"== 演练标记：{MARK} ==")

    header = ["标题", "日期", "链接", "情报类型", "正文"]
    good_rows = [
        header,
        [f"{MARK} 钙钛矿涂层新工艺", "2026-10-01", f"https://t34/x1", "新闻", "正文一"],
        [f"{MARK} 固态电解质综述", "2026-10-02", f"https://t34/x2", "文献", "正文二"],
        [f"{MARK} 组件回收研究", "2026-10-03", f"https://t34/x3", "文献", "正文三"],
    ]
    mapping = {"title": "标题", "date": "日期", "url": "链接", "type": "情报类型", "body": "正文"}
    blob = xlsx_bytes(good_rows)

    # 1) 预览：表头识别（含「情报类型」列）
    body, ct = multipart({}, {"file": ("t34.xlsx", blob, XLSX_MIME)})
    st, prev = api(jwt, "POST", "/api/uploads/row-preview", raw=body, content_type=ct)
    sheets = prev.get("sheets", [])
    headers = sheets[0].get("headers", []) if sheets else []
    check("预览返回表头（含「情报类型」）", st == 200 and "情报类型" in headers, f"headers={headers}")

    # 2) 合法导入（严格模式：type 映射必填，news/literature 混合）
    fields = {"primary_section": "breadth", "breadth_source": "other", "row_mode": "true",
              "column_mapping": json.dumps(mapping, ensure_ascii=False)}
    body, ct = multipart(fields, {"files": ("t34.xlsx", blob, XLSX_MIME)})
    st, resp = api(jwt, "POST", "/api/uploads", raw=body, content_type=ct)
    up_id = (resp.get("files", [{}])[0].get("id")
             if isinstance(resp.get("files"), list) and resp.get("files") else None)
    gi = resp.get("row_import", {})
    check("合法表导入成功", st == 201 and bool(up_id), f"status={st} {str(resp)[:150]}")
    check("导入计数 imported=3", (gi.get("imported") == 3), f"row_import={str(gi)[:200]}")

    # 3) 类型落库 + 导航透出
    st, nav = api(jwt, "GET",
                  f"/api/breadth/manual-records?visibility=nav&limit=200")
    items = nav.get("records", [])
    mine = [i for i in items if MARK in str(i.get("title", ""))]
    by_url = {i.get("url"): i for i in mine}
    types = {by_url.get("https://t34/x1", {}).get("intelligence_type"),
             by_url.get("https://t34/x2", {}).get("intelligence_type"),
             by_url.get("https://t34/x3", {}).get("intelligence_type")}
    check("导航可见 3 条导入记录", len(mine) == 3, f"titles={[i.get('title') for i in mine]}")
    check("类型落库：新闻→news、文献→literature", types == {"news", "literature"},
          f"intelligence_types={types}")

    # 4) 索引 chunk_metadata 带类型（canonical-qa 只读检索，T8 无鉴权边界）
    deadline = time.time() + 90
    searchable = None
    detail: dict = {}
    while time.time() < deadline:
        st, detail = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        if st == 200 and detail.get("searchable"):
            searchable = True
            break
        if st == 200 and detail.get("status") in ("index_failed", "import_failed"):
            break
        time.sleep(3)
    check("索引完成（index-status 权威判定）", searchable is True,
          f"status={detail.get('status')} index={detail.get('index')}")

    q = urllib.parse.quote(f"{MARK}")
    cite_types: set = set()
    try:
        r = urllib.request.urlopen(CANONICAL + f"/api/search?q={q}&sources=breadth&top_k=20")
        sr = json.load(r)
        for c in (sr.get("citations") or sr.get("results") or []):
            if MARK in str(c.get("title", "")):
                cm = c.get("chunk_metadata") or {}
                cite_types.add(cm.get("intelligence_type"))
    except Exception as e:
        print(f"  [warn] canonical search: {e}")
    check("检索引用 chunk_metadata 带 intelligence_type", cite_types <= {"news", "literature"} and cite_types,
          f"cited types={cite_types}")

    # 5) 非法类型整文件拒绝（400，无部分入库）
    bad_rows = [
        header,
        [f"{MARK} 好行", "2026-10-04", "https://t34/y1", "新闻", "正文"],
        [f"{MARK} 坏行", "2026-10-05", "https://t34/y2", "综述", "非法类型值"],
    ]
    bad_blob = xlsx_bytes(bad_rows)
    fields = {"primary_section": "breadth", "breadth_source": "other", "row_mode": "true",
              "column_mapping": json.dumps(mapping, ensure_ascii=False)}
    body, ct = multipart(fields, {"files": ("t34-bad.xlsx", bad_blob, XLSX_MIME)})
    st, resp = api(jwt, "POST", "/api/uploads", raw=body, content_type=ct)
    check("非法类型整文件拒绝（400）", st == 400, f"status={st} {str(resp)[:200]}")
    check("报错定位到物理行与原值", ("第 3 行" in str(resp) or "行 3" in str(resp) or ": 3" in str(resp)),
          str(resp)[:200])
    st, nav = api(jwt, "GET", f"/api/breadth/manual-records?visibility=nav&limit=200")
    leaked = [i for i in nav.get("records", []) if "t34/y" in str(i.get("url", ""))]
    check("无部分入库（好行也未写入）", not leaked, f"leaked={leaked}")

    # 6) 修复脚本 dry-run：新导入行为一致 → 无待修复
    r = subprocess.run(
        ["docker", "exec", "tech-boundary-db-api-1",
         "python", "/app/scripts/repair_row_intelligence_types.py", "--dry-run"],
        capture_output=True, text=True, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    check("修复脚本 dry-run 可修复 0", r.returncode == 0 and "可修复：0" in out,
          out.strip().replace("\n", " | ")[:200])

    print(f"\n结果：{len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("FAILED:", "; ".join(FAIL))
    if not args.keep and up_id:
        try:
            st, _ = api(jwt, "DELETE", f"/api/uploads/{up_id}")
            print(f"清理 upload {up_id[:8]}: {st}")
        except Exception as e:
            print(f"清理失败：{e}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
