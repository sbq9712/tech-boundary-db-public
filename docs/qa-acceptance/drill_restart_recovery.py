#!/usr/bin/env python3
"""任务验收演练（公司服务器实测）：重启一致性 + 索引损坏恢复 + 刷新一致。

流程：
1) 逐行表格导入（3 行，含 news/literature）→ 等待 index-status 权威判定 indexed；
2) 重启 canonical-qa 容器 → 索引持久（搜索仍命中、DB 记录不变、状态仍 indexed）；
3) 人为损坏增量索引文件 → 重启 → 如实降级（health.corrupt / index-status
   legacy_unknown + documents_missing）→ 搜索命中归零（不冒充有证据）；
4) 用户恢复路径：上传重试（幂等重放）→ 回到 indexed/searchable → 搜索恢复命中；
5) 浏览器刷新一致：列表页 index_detail 与详情端点一致（刷新后显示不变）；
6) 清理：删除上传 → 墓碑 → 搜索归零。

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
QA = "http://localhost:8767"
CANON = "tech-boundary-db-canonical-qa-1"
API_CONT = "tech-boundary-db-api-1"
INDEX_FILE = "/app/data/lightrag/incremental/index.pkl"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, evidence: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" | {evidence}" if evidence else ""))
    (PASS if ok else FAIL).append(name)
    return ok


def login() -> str:
    env = open("/home/rhett/tech-boundary-db/.env").read()
    u = re.search(r"TECHDB_INITIAL_ADMIN_USERNAME=(.*)", env).group(1).strip()
    p = re.search(r"TECHDB_INITIAL_ADMIN_PASSWORD=(.*)", env).group(1).strip()
    req = urllib.request.Request(
        API + "/api/auth/login", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": u, "password": p}).encode())
    return json.load(urllib.request.urlopen(req))["access_token"]


def api(jwt: str, method: str, path: str, raw: bytes | None = None,
        content_type: str = "application/json"):
    body = (raw if raw is not None
            else json.dumps({}).encode() if method in ("POST", "PATCH", "DELETE") else None)
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
    bnd = "----drillrrboundary"
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


def qa_health() -> dict:
    return json.load(urllib.request.urlopen(QA + "/api/health"))


def search_hits(q: str, sources: str = "breadth") -> int:
    u = QA + "/api/search?q=" + urllib.parse.quote(q) + f"&sources={sources}&top_k=10"
    try:
        d = json.load(urllib.request.urlopen(u))
        rs = d.get("results") or []
        return sum(1 for c in rs if q in str(c.get("title", "")))
    except Exception:
        return -1


def wait_status(jwt: str, up_id: str, want: set[str], timeout: int = 120):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        st, d = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        last = d if st == 200 else {"http": st}
        if st == 200 and (d.get("searchable") or d.get("status") in want):
            return d
        time.sleep(3)
    return last


def wait_qa_ready(timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            h = qa_health()
            if h.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(4)
    return False


MARK = "drr" + str(int(time.time()))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    jwt = login()
    up_id = None
    print(f"== 演练标记：{MARK} ==")

    try:
        # 1) 导入 3 行表格
        rows = [["标题", "日期", "链接", "情报类型", "正文"],
                [f"{MARK} 钙钛矿涂层", "2026-10-01", "https://drr/x1", "新闻", "正文一"],
                [f"{MARK} 固态电解质", "2026-10-02", "https://drr/x2", "文献", "正文二"],
                [f"{MARK} 组件回收", "2026-10-03", "https://drr/x3", "文献", "正文三"]]
        mapping = {"title": "标题", "date": "日期", "url": "链接",
                   "type": "情报类型", "body": "正文"}
        blob = xlsx_bytes(rows)
        body, ct = multipart(
            {"primary_section": "breadth", "breadth_source": "other", "row_mode": "true",
             "column_mapping": json.dumps(mapping, ensure_ascii=False)},
            {"files": ("drr.xlsx", blob, XLSX_MIME)})
        st, resp = api(jwt, "POST", "/api/uploads", raw=body, content_type=ct)
        files = resp.get("files") or [{}]
        up_id = files[0].get("id")
        check("导入成功（3 行）", st == 201 and up_id
              and (resp.get("row_import") or {}).get("imported") == 3,
              f"status={st} row_import={resp.get('row_import')}")

        d = wait_status(jwt, up_id, want={"index_failed", "legacy_unknown"})
        check("初始索引完成（searchable）", bool(d.get("searchable")),
              f"status={d.get('status')} index={d.get('index')}")
        base_hits = search_hits(MARK)
        check("初始搜索命中 3", base_hits == 3, f"hits={base_hits}")
        base_records = int(qa_health().get("incremental_records") or 0)

        # 2) 重启一致：容器重启后索引持久
        subprocess.run(["docker", "restart", CANON], capture_output=True, timeout=120)
        ok = wait_qa_ready()
        check("canonical-qa 重启后健康", ok)
        h = qa_health()
        hits = search_hits(MARK)
        st2, d2 = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        check("重启后索引持久（搜索仍命中 3）", hits == 3,
              f"hits={hits} incremental_records={h.get('incremental_records')}")
        check("重启后状态仍 indexed/searchable",
              st2 == 200 and d2.get("status") == "indexed" and bool(d2.get("searchable")),
              f"status={d2.get('status')} searchable={d2.get('searchable')}")

        # 3) 索引损坏：备份 → 写坏增量索引文件 → 重启 → 如实降级
        #    （损坏是破坏性操作：先备份 index.pkl，演练末尾恢复原索引）
        backup = f"/tmp/drr-index-backup-{MARK}.pkl"
        r = subprocess.run(["docker", "cp", f"{CANON}:{INDEX_FILE}", backup],
                           capture_output=True, timeout=120)
        check("索引文件已备份", r.returncode == 0 and __import__("os").path.getsize(backup) > 0,
              f"backup={backup}")
        r = subprocess.run(["docker", "exec", CANON, "sh", "-c",
                            f"printf 'CORRUPTED-BY-DRILL' > {INDEX_FILE}"],
                           capture_output=True, timeout=60)
        subprocess.run(["docker", "restart", CANON], capture_output=True, timeout=120)
        wait_qa_ready()
        h = qa_health()
        check("损坏后 health 如实（corrupt=true / 记录清零）",
              bool(h.get("incremental_corrupt")) or int(h.get("incremental_records") or 0) == 0,
              f"corrupt={h.get('incremental_corrupt')} records={h.get('incremental_records')} "
              f"epoch={h.get('incremental_reset_epoch')}")
        hits = search_hits(MARK)
        check("损坏后搜索命中归零（不冒充有证据）", hits == 0, f"hits={hits}")
        st3, d3 = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        check("损坏后状态如实降级（legacy_unknown + missing）",
              st3 == 200 and d3.get("status") in ("legacy_unknown", "index_failed")
              and not d3.get("searchable"),
              f"status={d3.get('status')} searchable={d3.get('searchable')} "
              f"missing={d3.get('index', {}).get('documents_missing')}")

        # 4) 用户恢复路径：重试（幂等重放）→ 恢复
        st4, r4 = api(jwt, "POST", f"/api/uploads/{up_id}/embedding/retry")
        check("重试受理", st4 in (200, 202), f"status={st4} {str(r4)[:120]}")
        d4 = wait_status(jwt, up_id, want={"index_failed"}, timeout=180)
        hits = search_hits(MARK)
        check("恢复后状态 indexed/searchable",
              bool(d4.get("searchable")) and d4.get("status") == "indexed",
              f"status={d4.get('status')} searchable={d4.get('searchable')}")
        check("恢复后搜索命中恢复 3", hits == 3, f"hits={hits}")

        # 4b) 恢复原索引（非演练数据：ATSC PDF/管线语料等，损坏前备份）
        #     docker cp 落盘属主是宿主 uid——服务进程是 qa 用户，必须 chown，
        #     否则重启 load 因 PermissionError 判损坏（演练首轮实测发现）
        subprocess.run(["docker", "stop", CANON], capture_output=True, timeout=120)
        subprocess.run(["docker", "cp", backup, f"{CANON}:{INDEX_FILE}"],
                       capture_output=True, timeout=120)
        subprocess.run(["docker", "start", CANON], capture_output=True, timeout=120)
        # docker cp 落盘属主是宿主 uid；docker exec 只能对运行中容器执行——
        # 先启动（load 因属主失败但不落盘，仅内存清空），改属主后再重启加载。
        subprocess.run(["docker", "exec", "-u", "root", CANON, "chown", "qa:qa",
                       INDEX_FILE], capture_output=True, timeout=60)
        subprocess.run(["docker", "restart", CANON], capture_output=True, timeout=120)
        ok = wait_qa_ready()
        h = qa_health()
        check("原索引已恢复（其余文档回归，记录数回到损坏前）",
              ok and not h.get("incremental_corrupt")
              and int(h.get("incremental_records") or 0) >= base_records,
              f"records={h.get('incremental_records')}（损坏前 {base_records}） "
              f"corrupt={h.get('incremental_corrupt')}")
        hits = search_hits(MARK)
        check("恢复原索引后演练记录仍命中（备份含演练前状态+重放写入）",
              hits >= 3, f"hits={hits}")

        # 5) 浏览器刷新一致：列表 index_detail 与详情一致
        st5, lst = api(jwt, "GET", "/api/uploads?limit=100")
        item = next((f for f in (lst.get("files") or [])
                     if f.get("id") == up_id), None)
        _, det = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        det_status = det.get("status")
        list_status = ((item or {}).get("index_detail") or {}).get(
            "status") or (item or {}).get("ingestion_status")
        check("刷新一致（列表与详情状态一致）", bool(item) and list_status == det_status,
              f"list={list_status} detail={det_status}")

    finally:
        if not args.keep and up_id:
            try:
                st, _ = api(jwt, "DELETE", f"/api/uploads/{up_id}")
                print(f"清理 upload {up_id[:8]}: {st}")
                time.sleep(4)
                hits = search_hits(MARK)
                check("清理后搜索归零（墓碑生效）", hits == 0, f"hits={hits}")
            except Exception as e:
                print(f"清理失败：{e}")

    print(f"\n结果：{len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("FAILED:", "; ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
