#!/usr/bin/env python3
"""任务 1.4 演练（方法学修订版）：重启一致性 + 索引损坏恢复 + 刷新一致。

方法学修订（对旧版的四项批评逐条落实）：
1) 【隔离】损坏演练不再触碰共享索引——旧版「备份共享 index.pkl → 写坏 →
   恢复」在承载业务数据的公司索引上原样重跑破坏性操作，任何一步中断都
   把共享栈留在损坏态。新版损坏/恢复全部在一次性隔离实例
   （独立容器 + 独立匿名卷 + 随机 token）上进行，容器销毁即清理；
   共享栈只做非破坏操作（导入→重启→删除）。
2) 【子进程返回码】所有 docker 子进程显式校验 returncode + 暴露 stderr，
   失败即中止所在阶段（不再让后续断言在错误状态上给出误导性 FAIL）。
3) 【finally 兜底】finally 阶段无条件清理：隔离容器销毁、共享栈演练数据
   删除（幂等）；共享栈从未被损坏，无需恢复步骤（防御性注释说明）。
4) 【真实页面刷新】刷新一致检查经真实浏览器页面（Playwright 加载资料库
   页面读取渲染状态），API 对比仅作辅助交叉验证；浏览器不可用时显式
   SKIP（可见、可审计），不静默降级为 API 对比。

Phase A（共享栈，非破坏）：导入 3 行 → indexed → 搜索命中 3 → 重启
  canonical → 索引持久/状态一致 → 真实页面刷新一致 → 删除 → 墓碑归零。
Phase B（隔离实例，破坏性）：种子 upsert → 命中 → 写坏索引 → 重启 →
  health 如实 corrupt + 搜索归零 → 重放 upsert 恢复命中 → 销毁容器。

只读端点无鉴权（T8 设计，Docker 内网边界）；写端点走 API JWT /
X-TechDB-Index-Token。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = os.getenv("DRILL_API", "http://localhost:8080")
QA = os.getenv("DRILL_QA", "http://localhost:8767")
CANON = os.getenv("DRILL_CANON", "tech-boundary-db-canonical-qa-1")
CANON_IMAGE = os.getenv("DRILL_CANON_IMAGE", "techdb-canonical-qa:1005")
ISO_NAME = "drr-iso-" + secrets.token_hex(4)
ISO_PORT = os.getenv("DRILL_ISO_PORT", "18767")
INDEX_FILE = "/app/data/idx/index.pkl"  # 隔离实例专用路径（独立卷）

PASS: list[str] = []
FAIL: list[str] = []
SKIP: list[str] = []


def check(name: str, ok: bool, evidence: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" | {evidence}" if evidence else ""))
    (PASS if ok else FAIL).append(name)
    return ok


def skipped(name: str, why: str) -> None:
    print(f"  [SKIP] {name} | {why}")
    SKIP.append(name)


def run_checked(desc: str, *cmd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """修订 2：子进程显式校验——失败打印 stderr 并抛异常中止所在阶段。"""
    r = subprocess.run(list(cmd), capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print(f"  [ABORT] {desc} 失败 rc={r.returncode}：{cmd[0]} …")
        print("  stderr:", (r.stderr or b"").decode(errors="replace")[:400])
        raise RuntimeError(f"{desc} 失败（rc={r.returncode}）")
    return r


def login() -> str:
    env = (REPO / ".env").read_text()
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


def qa_health(base: str = QA) -> dict:
    return json.load(urllib.request.urlopen(base + "/api/health", timeout=30))


def search_hits(q: str, base: str = QA, token: str | None = None,
                title_key: str = "title") -> int:
    # top_k=50：编排检索中增量记录的融合排名可能低于基础语料 top-10
    #（3.4 演练实测：需 50 才能召回单条增量记录）——命中判定不受截断影响。
    u = base + "/api/search?q=" + urllib.parse.quote(q) + "&top_k=50"
    req = urllib.request.Request(u)
    if token:
        req.add_header("X-TechDB-Index-Token", token)
    try:
        d = json.load(urllib.request.urlopen(req, timeout=60))
        rs = d.get("results") or []
        return sum(1 for c in rs if q in str(c.get(title_key, "")))
    except Exception:
        return -1


def wait_status(jwt: str, up_id: str, timeout: int = 150):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        st, d = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        last = d if st == 200 else {"http": st}
        if st == 200 and (d.get("searchable") or d.get("status") in
                          ("index_failed", "legacy_unknown")):
            return d
        time.sleep(3)
    return last


def wait_ready(base: str, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if qa_health(base).get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(4)
    return False


def browser_refresh_check(jwt: str, up_id: str) -> None:
    """修订 4：真实页面刷新一致——渲染层状态 vs 详情端点，两轮刷新。"""
    name = "刷新一致（真实页面两轮刷新，渲染状态不变）"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        skipped(name, "宿主无 playwright，无法做真实页面验证（部署机请补装）")
        return
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_context().new_page()
            page.goto(API + "/login.html")
            page.evaluate("t => localStorage.setItem('auth_token', t)", jwt)
            page.goto(API + f"/#library?section=breadth&sub=other")
            page.wait_for_timeout(2500)
            seen = []
            for _ in range(2):
                row = page.locator(f"tr:has(button[data-lib-idx-detail='{up_id}'])")
                if row.count() == 0:
                    break
                seen.append(row.inner_text()[:200].replace("\n", " / "))
                page.reload()
                page.wait_for_timeout(2500)
            b.close()
        ok = len(seen) == 2 and seen[0].strip() == seen[1].strip()
        check(name, ok, f"round1={seen[0] if seen else '?'} round2={seen[1] if len(seen) > 1 else '?'}")
    except Exception as e:
        # 浏览器存在但启动失败（缺系统库等）——如实 SKIP 并给出原因
        skipped(name, f"浏览器启动失败：{e.__class__.__name__}: {str(e)[:120]}")


MARK = "drr" + str(int(time.time()))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def phase_a(jwt: str, keep: bool = False) -> None:
    print("== Phase A：共享栈（非破坏）导入/重启/刷新一致/清理 ==")
    up_id = None
    try:
        rows = [["标题", "日期", "链接", "情报类型", "正文"],
                [f"{MARK} 钙钛矿涂层", "2026-10-01", "https://drr/x1", "新闻", "正文一"],
                [f"{MARK} 固态电解质", "2026-10-02", "https://drr/x2", "文献", "正文二"],
                [f"{MARK} 组件回收", "2026-10-03", "https://drr/x3", "文献", "正文三"]]
        mapping = {"title": "标题", "date": "日期", "url": "链接",
                   "type": "情报类型", "body": "正文"}
        body, ct = multipart(
            {"primary_section": "breadth", "breadth_source": "other", "row_mode": "true",
             "column_mapping": json.dumps(mapping, ensure_ascii=False)},
            {"files": ("drr.xlsx", xlsx_bytes(rows), XLSX_MIME)})
        st, resp = api(jwt, "POST", "/api/uploads", raw=body, content_type=ct)
        files = resp.get("files") or [{}]
        up_id = files[0].get("id")
        check("导入成功（3 行）", st == 201 and up_id
              and (resp.get("row_import") or {}).get("imported") == 3,
              f"status={st} row_import={resp.get('row_import')}")

        d = wait_status(jwt, up_id)
        check("初始索引完成（searchable）", bool(d.get("searchable")),
              f"status={d.get('status')} states={d.get('states')}")
        hits = search_hits(MARK)
        check("初始搜索命中 3", hits == 3, f"hits={hits}")

        # 重启一致（非破坏操作）
        run_checked("重启 canonical-qa", "docker", "restart", CANON)
        check("canonical-qa 重启后健康", wait_ready(QA))
        h = qa_health()
        hits = search_hits(MARK)
        check("重启后索引持久（搜索仍命中 3）", hits == 3,
              f"hits={hits} incremental_records={h.get('incremental_records')}")
        st2, d2 = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        check("重启后状态仍 indexed/searchable",
              st2 == 200 and d2.get("status") == "indexed" and bool(d2.get("searchable")),
              f"status={d2.get('status')} searchable={d2.get('searchable')}")

        # 真实页面刷新一致 + API 交叉验证
        browser_refresh_check(jwt, up_id)
        st5, lst = api(jwt, "GET", "/api/uploads?limit=100")
        item = next((f for f in (lst.get("files") or []) if f.get("id") == up_id), None)
        _, det = api(jwt, "GET", f"/api/uploads/{up_id}/index-status")
        list_status = ((item or {}).get("index_detail") or {}).get(
            "status") or (item or {}).get("ingestion_status")
        check("API 交叉验证（列表与详情状态一致）",
              bool(item) and list_status == det.get("status"),
              f"list={list_status} detail={det.get('status')}")
    finally:
        if up_id and not keep:
            try:
                st, _ = api(jwt, "DELETE", f"/api/uploads/{up_id}")
                print(f"清理 upload {up_id[:8]}: {st}")
                # 删除请求本身失败必须计为 FAIL（Codex r4 P2-2：不能把失败降级为成功）
                check("清理删除请求成功", st in (200, 202, 204), f"st={st}")
                # 删除→worker→canonical 墓碑传播有时延：队列 worker 5s 轮询 +
                # 失败退避 30s 起，加网络/嵌入耗时，最坏 90-120s（Codex r4 P3-1）。
                # 判定契约是搜索归零（墓碑语义）；上传删除后 index-status 可能
                # 404，不能作为组合条件。总上限可用环境变量覆盖（默认 120s）。
                deadline_s = int(os.environ.get("DRILL_TOMBSTONE_TIMEOUT", "120"))
                hits, waited = -1, 0
                while waited < deadline_s:
                    time.sleep(4); waited += 4
                    hits = search_hits(MARK)
                    if hits == 0:
                        break
                check("清理后搜索归零（墓碑生效）", hits == 0,
                      f"hits={hits} waited={waited}s")
            except Exception as e:
                # 清理链路异常同样必须 FAIL——演练结论不能建立在未验证的清理之上
                check("清理链路无异常", False, f"exc={e!r}")


def iso_upsert(base: str, token: str, doc_id: str) -> None:
    req = urllib.request.Request(
        base + "/api/index/upsert", method="POST",
        headers={"Content-Type": "application/json",
                 "X-TechDB-Index-Token": token},
        data=json.dumps({
            "document_id": doc_id, "filename": "drr-iso.txt",
            "title": f"{MARK} 隔离演练记录", "primary_category": "未分类",
            "source_type": "breadth-import", "checksum_sha256": "iso-" + doc_id,
            "chunks": [{
                "chunk_id": doc_id + "-0",
                "text": f"{MARK} 隔离演练正文：钙钛矿涂层界面阻抗稳定性。",
                "title": f"{MARK} 隔离演练记录",
                "metadata": {"primary_section": "breadth",
                             "record_key_sha": "iso-" + doc_id,
                             "content_sha": "iso-v1-" + doc_id,
                             "intelligence_type": "news"},
            }],
        }).encode())
    r = urllib.request.urlopen(req, timeout=120)
    assert r.status == 200, r.read()[:200]


def phase_b() -> None:
    print("== Phase B：隔离实例（破坏性损坏/恢复，不触碰共享索引）==")
    iso_token = secrets.token_hex(16)
    iso_base = f"http://localhost:{ISO_PORT}"
    started = False
    try:
        run_checked(
            "启动隔离 canonical-qa（一次性实例）", "docker", "run", "-d", "--rm",
            "--name", ISO_NAME, "-p", f"127.0.0.1:{ISO_PORT}:8765",
            "-e", f"TECHDB_QA_INDEX_TOKEN={iso_token}",
            "-e", f"TECHDB_QA_INCREMENTAL_INDEX_PATH={INDEX_FILE}",
            CANON_IMAGE)
        started = True
        check("隔离实例健康", wait_ready(iso_base))

        doc_id = f"iso-{MARK}"
        iso_upsert(iso_base, iso_token, doc_id)
        time.sleep(2)
        q = MARK
        hits = search_hits(q, base=iso_base, token=iso_token)
        check("隔离种子命中 1", hits == 1, f"hits={hits}")
        n0 = int(qa_health(iso_base).get("incremental_records") or 0)
        check("隔离索引持久化落盘", n0 >= 1, f"records={n0}")

        # 写坏索引 → 重启 → 如实降级
        run_checked("写坏隔离索引文件", "docker", "exec", ISO_NAME, "sh", "-c",
                    f"printf 'CORRUPTED-BY-DRILL' > {INDEX_FILE}")
        run_checked("重启隔离实例", "docker", "restart", ISO_NAME)
        check("损坏实例重启后健康（降级存活）", wait_ready(iso_base))
        h = qa_health(iso_base)
        check("health 如实（corrupt=true / 记录清零）",
              bool(h.get("incremental_corrupt")) or
              int(h.get("incremental_records") or 0) == 0,
              f"corrupt={h.get('incremental_corrupt')} "
              f"records={h.get('incremental_records')}")
        hits = search_hits(q, base=iso_base, token=iso_token)
        check("损坏后搜索命中归零（不冒充有证据）", hits == 0, f"hits={hits}")

        # 恢复路径：损坏后重放 upsert（幂等重建）→ 命中恢复
        iso_upsert(iso_base, iso_token, doc_id)
        time.sleep(2)
        hits = search_hits(q, base=iso_base, token=iso_token)
        h2 = qa_health(iso_base)
        check("重放 upsert 后命中恢复", hits == 1,
              f"hits={hits} records={h2.get('incremental_records')}")
    finally:
        if started:
            try:
                run_checked("销毁隔离实例", "docker", "rm", "-f", ISO_NAME, timeout=60)
                print("  隔离实例已销毁（--rm 卷随容器回收）")
            except Exception as e:
                # Codex r5 P3-4：隔离容器清理失败必须计入 FAIL（残留容器会
                # 占用 ISO_NAME/端口，污染下一轮演练）
                check("隔离实例清理成功", False,
                      f"请手动 docker rm -f {ISO_NAME}：{e}")
        # 防御性说明：共享栈在本方法学下从未被写坏（损坏仅发生在隔离实例），
        # 故无需「恢复备份」步骤；若未来有人把破坏步骤搬回共享栈，必须
        # 在 finally 里补备份恢复——旧版 Drill 的教训。


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="保留 Phase A 演练数据（默认删除）")
    args = ap.parse_args()
    jwt = login()
    print(f"== 演练标记：{MARK} ==")
    try:
        phase_a(jwt, keep=args.keep)
        # Codex r5 P3-4：Phase A 有 FAIL 时跳过 Phase B——在错误状态上继续
        # 破坏性演练只会产出误导性结论（11 号规则：失败即中止所在阶段）。
        if FAIL:
            print(f"[SKIP] Phase B 跳过：Phase A 已有 {len(FAIL)} 项 FAIL")
        else:
            phase_b()
    except (KeyboardInterrupt, SystemExit) as e:
        # 中断也是失败：计入 FAIL 后按非零码退出，不静默吞掉
        check("演练未被中断", False, f"interrupted: {e!r}")
        print(f"\n结果：{len(PASS)} PASS / {len(FAIL)} FAIL / {len(SKIP)} SKIP")
        print("FAILED:", "; ".join(FAIL))
        return 1
    print(f"\n结果：{len(PASS)} PASS / {len(FAIL)} FAIL / {len(SKIP)} SKIP")
    if FAIL:
        print("FAILED:", "; ".join(FAIL))
    if SKIP:
        print("SKIPPED:", "; ".join(SKIP))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
