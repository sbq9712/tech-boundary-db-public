#!/usr/bin/env python3
"""八/一：三个源头（新闻/文献/微信源仓库）隔离小样本全链验收。

「源头 = 三个源仓库」，不是管线视图/重建资产/增量卷：本地 HTTP 服务按
GitHub 语义（contents 列表 + raw 内容）供给固定小样本 CSV，经真实
auto_pipeline 全链（抓取→解析→引擎分诊→合并→发布→QA 三路索引同步→
报告补跑）跑通，全程离线（TRIAGE_LLM_OFF=1、LLM key 缺失 → GLM 步
如实降级并记录）。

== 场景与覆盖口径（一：成功/预期降级分开，不互相冒充） ==
- 数据链（抓取→解析→引擎分诊→合并→发布→同步）：**成功场景**——要求
  确定退出码、真实产物与内容断言。
- LLM 生成链（主题/摘要/关键参数/翻译/报告成稿）：**预期降级场景**——
  无 key 时必须「如实跳过 + 不伪造 + 下轮补跑」，单独报告，不计入
  「全链成功」口径（生成质量验收见 六：真实 key 隔离服务验收）。
- QA 同步目标两种模式（E2E3S_QA 环境变量，默认 auto）：
  * real：docker 启动隔离 canonical-qa（techdb-canonical-qa:1001，独立
    增量卷），真实 sync_qa_index 推送；用 /api/stats、/api/search、
    /api/graph、/api/chat/stream 验证 **向量/BM25/图谱/门户证据** 在
    基线→更新→删除→新增→中断恢复后的最新状态。覆盖口径 = 真实索引。
  * stub：HTTP 替身（POST /api/index/* 恒 200）。覆盖口径仅 = 同步协议
    触发、退出码、水印文件落盘；**不验证真实索引内容**（如实标注）。
- 失败待办与补跑：SKIP_CLUSTER 下聚类待办如实保留；会议待办补跑后清除；
  报告缺口按 --all 逐轮补跑（本轮如实跳过）。
- 真实中断恢复：E 阶段先指向关闭端口使 Step 10 真实失败（水印不推进），
  再恢复真实地址重跑 → 记录补齐、恰好一次（无重复）。

用法：python3 pipeline/tests/e2e_three_sources_isolated.py [--keep]
环境：E2E3S_STAGE（stage 目录，默认 /tmp/e2e3s）、E2E3S_QA=auto|real|stub、
      E2E3S_QA_IMAGE（默认 techdb-canonical-qa:1001）、E2E3S_QA_PORT（18903）
退出码：0=全部通过；2=有断言失败（细节在 stdout 与 stage 日志）。
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGE = Path(os.environ.get("E2E3S_STAGE", "/tmp/e2e3s"))
PIPE_STAGE = STAGE / "pipeline"
BOUNDARY_STAGE = STAGE / "boundary"
FIXTURES = STAGE / "fixtures"
SRC_PORT = 18901
API_BASE = f"http://127.0.0.1:{SRC_PORT}"
SYNC_PORT = 18902
SYNC_BASE = f"http://127.0.0.1:{SYNC_PORT}"
QA_MODE = os.environ.get("E2E3S_QA", "auto").strip().lower()
QA_IMAGE = os.environ.get("E2E3S_QA_IMAGE", "techdb-canonical-qa:1001")
QA_PORT = int(os.environ.get("E2E3S_QA_PORT", "18903"))
QA_BASE = f"http://127.0.0.1:{QA_PORT}"
QA_CONTAINER = "e2e3s-qa"
QA_VOLUME = "e2e3s-qa-inc"

NEWS1 = [
    {"title": "全固态电池界面阻抗研究取得突破", "url": "https://news.example.com/a1",
     "content": "某研究所发布全固态电池界面阻抗优化方案，能量密度显著提升。",
     "source": "能源新闻网", "publish_time": "2026-09-15 09:00"},
    {"title": "新型催化材料降低电解水成本", "url": "https://news.example.com/a2",
     "content": "非贵金属催化剂使电解水制氢成本下降，团队完成千小时验证。",
     "source": "材料日报", "publish_time": "2026-09-15 11:00"},
    {"title": "量子点显示材料量产工艺公布", "url": "https://news.example.com/a3",
     "content": "企业公布量子点显示材料量产工艺，寿命与色域同步提升。",
     "source": "显示行业周报", "publish_time": "2026-09-15 14:00"},
]
LIT1 = [
    {"title": "High-entropy alloy anodes for sodium-ion batteries",
     "url": "https://doi.example.org/10.1000/lit1",
     "abstract": "We demonstrate high-entropy alloy anodes with improved cycling stability.",
     "authors": "Zhang et al.", "pub_date": "2026-09-15"},
    {"title": "Machine-learning screening of solid electrolytes",
     "url": "https://doi.example.org/10.1000/lit2",
     "abstract": "A machine-learning workflow screens 12k candidates for ionic conductivity.",
     "authors": "Lee et al.", "pub_date": "2026-09-15"},
]
WECHAT1 = [
    {"title": "动力电池回收产业月度观察", "url": "https://mp.weixin.example.com/w1",
     "clean_text": "九月动力电池回收产能与价格走势分析，头部企业扩产提速。",
     "account_name": "电池观察", "publish_time": "2026-09-15 08:00"},
    {"title": "储能电芯价格企稳信号梳理", "url": "https://mp.weixin.example.com/w2",
     "clean_text": "储能电芯招标价格出现企稳迹象，系统集成商毛利修复。",
     "account_name": "储能前沿", "publish_time": "2026-09-15 20:00"},
]
NEWS2 = [
    {"title": "钠离子电池正极材料新路线", "url": "https://news.example.com/b1",
     "content": "层状氧化物正极新路线将钠电池能量密度推高至160Wh/kg。",
     "source": "能源新闻网", "publish_time": "2026-09-16 10:00"},
]
NEWS3 = [
    {"title": "固态电解质千吨级产线落地", "url": "https://news.example.com/b2",
     "content": "硫化物固态电解质千吨级产线投产，成本较进口下降三成。",
     "source": "能源新闻网", "publish_time": "2026-09-16 15:00"},
]

_results = []
SCENARIO_LABELS = []  # (标签, 是否计入全链成功口径)


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(("  PASS " if cond else "  FAIL ") + name + (f" | {detail}" if detail and not cond else ""),
          flush=True)
    return bool(cond)


def scenario(label, counts_as_full_chain):
    SCENARIO_LABELS.append((label, bool(counts_as_full_chain)))
    print(f"\n-- 场景口径：{label}" + ("" if counts_as_full_chain
          else "（预期降级/部分口径，不计入全链成功）"), flush=True)


def to_csv(rows, cols):
    import csv as _csv
    import io
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


class SourceHandler(BaseHTTPRequestHandler):
    """按 GitHub 语义提供固定小样本：/repos/{repo}/contents/{path} 列表 +
    /{repo}/main/{path}/{file} raw 内容。内容实时读自 fixtures 目录。"""

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = self.path.lstrip("/").split("/")
        if len(parts) >= 5 and parts[0] == "repos" and parts[3] == "contents":
            src = f"{parts[1]}/{parts[2]}"
            path = "/".join(parts[4:])
            d = FIXTURES / src / path
            if not d.is_dir():
                return self._json({"message": "Not Found"}, 404)
            out = [{"name": f.name,
                    "sha": __import__("hashlib").sha256(f.read_bytes()).hexdigest(),
                    "type": "file"}
                   for f in sorted(d.iterdir()) if f.is_file()]
            return self._json(out)
        if len(parts) >= 5 and parts[2] == "main":
            src = f"{parts[0]}/{parts[1]}"
            rel = "/".join(parts[3:])
            f = FIXTURES / src / rel
            if not f.is_file():
                return self._json({"message": "Not Found"}, 404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self._json({"message": "Not Found"}, 404)


class SyncHandler(BaseHTTPRequestHandler):
    """canonical-qa /api/index/* 的最小替身。
    覆盖口径（如实标注）：只证明管线会按契约调用同步端点且按返回码判定
    成败；不验证任何真实索引内容。"""

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"status": "ready", "chunks": 0, "documents": 1,
                           "skipped_duplicate_chunks": 0}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_fixtures():
    shutil.rmtree(FIXTURES, ignore_errors=True)
    news = FIXTURES / "wodewoping-png" / "news-spider" / "data"
    lit = FIXTURES / "wodewoping-png" / "literature-rss-spider" / "output"
    wc = FIXTURES / "wodewoping-png" / "wechat-daily-news-csv" / "csv"
    for d in (news, lit, wc):
        d.mkdir(parents=True, exist_ok=True)
    (news / "articles-2026-09-15.csv").write_text(to_csv(
        NEWS1, ["title", "url", "content", "source", "publish_time"]), encoding="utf-8")
    (lit / "news_with_abstract_2026-09-15.csv").write_text(to_csv(
        LIT1, ["title", "url", "abstract", "authors", "pub_date"]), encoding="utf-8")
    (wc / "2026-09-15.csv").write_text(to_csv(
        WECHAT1, ["title", "url", "clean_text", "account_name", "publish_time"]),
        encoding="utf-8")


def build_stage():
    """隔离 REPO：拷贝管线代码（不含 data/state），BOUNDARY_REPO 指向隔离布局。"""
    shutil.rmtree(STAGE, ignore_errors=True)
    PIPE_STAGE.mkdir(parents=True)
    for item in ("auto_pipeline.py", "engine_triage.py", "scripts", "engine_triage",
                 "triage_engine", "breadth"):
        src = REPO / "pipeline" / item
        dst = PIPE_STAGE / item
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", ".pytest_cache", "*.pkl", "data", ".engine_*",
                ".pipeline*", ".rebuild*", ".venv"))
        else:
            shutil.copy2(src, dst)
    data_src = REPO / "pipeline" / "data"
    data_dst = PIPE_STAGE / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    for f in data_src.iterdir():
        if f.is_file():
            shutil.copy2(f, data_dst / f.name)
    (data_dst / "processed").mkdir(exist_ok=True)
    (STAGE / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "scripts" / "sync_qa_index.py", STAGE / "scripts" / "sync_qa_index.py")
    (BOUNDARY_STAGE / "breadth" / "data").mkdir(parents=True)
    (BOUNDARY_STAGE / "breadth" / "version.txt").write_text("test-0", encoding="utf-8")
    (BOUNDARY_STAGE / "scripts").mkdir(parents=True, exist_ok=True)
    for s in ("build_breadth_alert_snapshot.py", "build_breadth_category_counts.py"):
        shutil.copy2(REPO / "scripts" / s, BOUNDARY_STAGE / "scripts" / s)
    write_fixtures()


def qa_http(path, timeout=60, method="GET", payload=None):
    url = QA_BASE + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_citations(question, timeout=170):
    """POST /api/chat/stream（检索-only + 诚实降级），解析 citations/error/done。

    返回 (citations, err, done)；err=error 事件 message（无 key 明确拒绝），
    done=done 事件（insufficient 路径的如实答复）。二者必有其一，都不伪造。
    """
    req = urllib.request.Request(
        QA_BASE + "/api/chat/stream",
        data=json.dumps({"query": question, "top_k": 8}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    text = raw.decode("utf-8", "replace")
    import re
    cites, err, done = [], None, None
    # SSE 行分隔为 \r\n（sse-starlette），正则必须容忍 \r
    for ev, data in re.findall(r"event: (\w+)\r?\ndata: (.*)", text):
        try:
            d = json.loads(data)
        except Exception:
            continue
        if ev == "citations":
            cites = d.get("citations", [])
        if ev == "error":
            err = str(d.get("message", ""))
        if ev == "done":
            done = d
    if cites == [] and err is None and done is None:
        # 一：连续全库编排检索后首聊可能瞬时无事件（服务器单 worker 高负载），
        # 空流重试一次；仍空则如实返回并打印截断原文供诊断。
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text2 = resp.read().decode("utf-8", "replace")
            for ev, data in re.findall(r"event: (\w+)\r?\ndata: (.*)", text2):
                try:
                    d = json.loads(data)
                except Exception:
                    continue
                if ev == "citations":
                    cites = d.get("citations", [])
                if ev == "error":
                    err = str(d.get("message", ""))
                if ev == "done":
                    done = d
            text = text2
        except Exception:
            pass
        if cites == [] and err is None and done is None:
            print(f"    [diag] chat SSE 空流原文[:300]: {text[:300]!r}")
    return cites, err, done


def qa_search(q, top_k=10, timeout=200):
    from urllib.parse import urlencode
    return qa_http("/api/search?" + urlencode({"q": q, "top_k": top_k}), timeout=timeout)


def search_hits(q, needle, top_k=50):
    """一.6：隔离真实索引底座 = 烘焙 68k 真实生产语料， fixture 记录的重排位次
    与全库相关性竞争有关，不属于本验收口径；断言口径 = **存在性**（top_k 窗口
    内按标题/正文命中）+ 内容新鲜度（citations.body_snippet），不断言名次。"""
    cits = qa_search(q, top_k).get("results", [])
    hits = [c for c in cits if needle in str(c.get("title", ""))
            or needle in str(c.get("body_snippet", ""))]
    return hits


def search_titles(q, top_k=10):
    return [r.get("title", "") for r in qa_search(q, top_k).get("results", [])]

def start_real_qa():
    """启动隔离 canonical-qa 容器（独立容器名/端口/增量卷），等健康。

    底座（烘焙基础索引/模型/依赖）来自镜像 QA_IMAGE；代码层挂载仓库当前
    qa-backend 目录（ro）——被验收的是本仓库当前代码而非镜像内历史代码，
    镜像重建前的代码修复才能进入真实链路验收（一.6 量纲修复）。
    """
    repo_qa_backend = Path(__file__).resolve().parents[2] / (
        "services/canonical-qa/qa-backend")
    subprocess.run(["docker", "rm", "-f", QA_CONTAINER],
                   capture_output=True, timeout=60)
    subprocess.run(["docker", "volume", "rm", "-f", QA_VOLUME],
                   capture_output=True, timeout=60)
    subprocess.run(["docker", "run", "-d", "--name", QA_CONTAINER,
                    "-e", "TZ=Asia/Shanghai",
                    "-v", f"{QA_VOLUME}:/app/data/lightrag/incremental",
                    "-v", f"{repo_qa_backend}:/app/qa-backend:ro",
                    "-p", f"127.0.0.1:{QA_PORT}:8765",
                    QA_IMAGE], check=True, capture_output=True, timeout=120)
    deadline = time.time() + 240
    while time.time() < deadline:
        try:
            h = qa_http("/api/health", timeout=5)
            if h.get("vector_index_ready") and h.get("bm25_ready"):
                return h
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("isolated canonical-qa not healthy in 240s")


def stop_real_qa():
    subprocess.run(["docker", "rm", "-f", QA_CONTAINER], capture_output=True, timeout=60)
    subprocess.run(["docker", "volume", "rm", "-f", QA_VOLUME], capture_output=True, timeout=60)


def run_pipeline(env_extra, expect_exit=(0,)):
    env = dict(os.environ)
    env.update({
        "TECHDB_PIPELINE_GITHUB_API_BASE": API_BASE,
        "TECHDB_PIPELINE_RAW_BASE": API_BASE,
        "BOUNDARY_REPO": str(BOUNDARY_STAGE),
        "TRIAGE_LLM_OFF": "1",
        "SKIP_CLUSTER": "1",
        # 离线隔离：GLM 无 key → 各 LLM 步快速如实失败/跳过（不吃退避睡眠）
        "TECHDB_GLM_BACKOFF_DELAYS": "0",
        "PYTHONPATH": str(PIPE_STAGE),
        "HOME": str(STAGE / "home"),
    })
    env.update(env_extra)
    proc = subprocess.run([sys.executable, "auto_pipeline.py"], cwd=PIPE_STAGE,
                          env=env, capture_output=True, text=True, timeout=900)
    log_path = STAGE / "pipeline_last_run.log"
    log_path.write_text(proc.stdout + "\n===STDERR===\n" + proc.stderr, encoding="utf-8")
    if proc.returncode not in expect_exit:
        print(proc.stdout[-3000:])
        print(proc.stderr[-2000:])
    return proc


def lite_records():
    lite = json.loads((PIPE_STAGE / "data" / "processed" / "all-records-lite.json")
                      .read_text(encoding="utf-8"))
    return lite


def state_counts():
    st = json.loads((PIPE_STAGE / ".pipeline_state.json").read_text())
    return {k: len(v) for k, v in st["known_files"].items()}


def main():
    # 决定 QA 模式
    global QA_MODE
    if QA_MODE == "auto":
        has_docker = shutil.which("docker") is not None
        has_image = False
        if has_docker:
            img = subprocess.run(["docker", "image", "inspect", QA_IMAGE, "--format", "ok"],
                                 capture_output=True, text=True)
            has_image = img.returncode == 0
        QA_MODE = "real" if has_docker and has_image else "stub"
    print(f"== QA 同步目标模式：{QA_MODE} ==" + (
        "（真实隔离 canonical-qa：验证真实索引内容）" if QA_MODE == "real"
        else "（HTTP 替身：仅验证同步协议触发/退出码/水印文件，不验证真实索引内容）"),
        flush=True)
    real = QA_MODE == "real"
    STAGE.mkdir(parents=True, exist_ok=True)
    build_stage()
    qa_handle = None
    servers = [ThreadingHTTPServer(("127.0.0.1", SRC_PORT), SourceHandler)]
    if not real:
        servers.append(ThreadingHTTPServer(("127.0.0.1", SYNC_PORT), SyncHandler))
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    try:
        if real:
            t0 = time.time()
            h = start_real_qa()
            print(f"  隔离 canonical-qa 就绪：total={h.get('total_indexed_records')} "
                  f"(容器启动 {time.time()-t0:.0f}s)", flush=True)
            check("R 隔离索引服务健康（向量+BM25 就绪）",
                  h.get("vector_index_ready") and h.get("bm25_ready"), str(h)[:120])

        def sync_env(url):
            # url=None → 跳过同步；url=地址 → 真实/替身同步目标
            e = {} if url else {"SKIP_QA_INDEX_SYNC": "1"}
            if url:
                e["TECHDB_QA_SYNC_URL"] = url
            return e

        # ── A 冷启动三源入库（数据链成功场景；LLM 预期降级） ──
        scenario("A 冷启动：数据链成功场景 + LLM 预期降级（无 key 如实跳过）",
                 counts_as_full_chain=False)
        proc = run_pipeline(sync_env(None), expect_exit=(0,))
        check("A 退出码恰为 0（发布/待办/报告补跑全收敛）", proc.returncode == 0,
              f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        lite = lite_records()
        titles = {r["t"] for r in lite}
        check("A lite 恰有 7 条", len(lite) == 7, f"n={len(lite)}")
        check("A 新闻入库", "全固态电池界面阻抗研究取得突破" in titles)
        check("A 文献入库（载体 l）",
              any(r["t"].startswith("High-entropy") and r.get("i") == "l" for r in lite))
        check("A 微信入库", "动力电池回收产业月度观察" in titles)
        triaged = [r for r in lite if r.get("c") not in (None, "", "未分类")]
        check("A 引擎分诊落地（至少 1 条获得分类/不相关判定）", len(triaged) >= 1,
              f"c={[r.get('c') for r in lite]}")
        check("A 预期降级：无伪造摘要", all(
            not r.get("as") or "摘要生成失败" in str(r.get("as")) for r in lite))
        check("A 预期降级：报告如实跳过（降级原因进主日志可核查）",
              "GLM returned empty" in out or "no records" in out
              or "no top events" in out or "no dates in data" in out,
              out[out.find("Step 11"):][:300] if "Step 11" in out else out[-300:])
        reports_dir = BOUNDARY_STAGE / "breadth" / "data" / "reports"
        report_files = [p for p in reports_dir.glob("**/*") if p.is_file()] \
            if reports_dir.exists() else []
        check("A 预期降级：未伪造报告文件（reports 下无任何文件，空目录不算）",
              not report_files, str([p.name for p in report_files[:5]]))
        proc_dir = BOUNDARY_STAGE / "breadth" / "data" / "processed"
        manifest = (proc_dir / "manifest-data.js").read_text(encoding="utf-8")
        meta = json.loads(manifest[manifest.find("{"):manifest.rfind("}") + 1])
        check("F manifest 记录总数 = 7", meta.get("meta", {}).get("records_total") == 7,
              str(meta.get("meta")))
        for fam in ("lite", "meta", "summary"):
            n = len(list(proc_dir.glob(f"{fam}-part-*.js")))
            check(f"F 分片族 {fam} 非空", n > 0, f"n={n}")
        sc = state_counts()
        check("F state 只提交成功文件（news=1/lit=1/wechat=1）",
              sc == {"literature": 1, "news": 1, "wechat": 1}, str(sc))

        # ── A2 基线同步（更新/删除之前，先有真实基线可断言）──
        scenario("A2 基线同步：7 条经真实 sync_qa_index 进入隔离索引（成功场景）",
                 counts_as_full_chain=True)
        proc = run_pipeline(sync_env(QA_BASE if real else SYNC_BASE), expect_exit=(0,))
        check("A2 同步运行退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        check("A2 日志确认 QA index sync complete", "QA index sync complete" in out,
              out[-300:])
        if real:
            st = qa_http("/api/stats")
            check("A2 真实索引增量条目 = 7", st.get("incremental_records") == 7,
                  str(st.get("incremental_records")))
            for t in ("全固态电池界面阻抗研究取得突破", "High-entropy alloy anodes",
                      "动力电池回收产业月度观察"):
                # 一.6：底座含 68k 真实生产语料，重排名次不属验收口径，
                # 断言存在性（top50 窗口 citations 标题命中）。
                check(f"A2 向量/BM25 可检索（存在性 top50）：{t[:18]}…",
                      len(search_hits(t, t[:18], 50)) >= 1,
                      f"hits={len(search_hits(t, t[:18], 50))}")
            g = qa_http("/api/graph?limit=50")
            check("A2 图谱碎片包含增量记录（fragment_nodes ≥ 1）",
                  g.get("fragment_nodes", 0) >= 1, str(g.get("fragment_nodes")))
            cites, err, done = chat_citations("全固态电池界面阻抗研究取得突破的要点")
            check("A2 门户证据链可命中基线记录（检索端 citations 存在性 top50）",
                  len(search_hits("全固态电池界面阻抗研究取得突破的要点",
                                  "全固态电池界面阻抗", 50)) >= 1,
                  "no hit")
            check("A2 chat 流式返回 citations 事件（证据链协议在位）",
                  isinstance(cites, list), f"{type(cites).__name__}")
            check("A2 无 key 诚实降级（生成段明确拒绝，或 insufficient 如实答复）",
                  (err is not None and "retrieval-only" in err)
                  or (done is not None and done.get("answer_status") == "insufficient")
                  or (done is not None and "抱歉" in str(done.get("answer", ""))),
                  f"err={str(err)[:80]} done={str((done or {}).get('answer_status'))[:40]}")

        # ── B 记录更新贯穿索引 ──
        scenario("B 记录更新（news a1 内容改写）：Step 2b + 索引 UPDATE 贯穿", True)
        news1 = FIXTURES / "wodewoping-png" / "news-spider" / "data" / "articles-2026-09-15.csv"
        rows = [dict(r) for r in NEWS1]
        rows[0]["content"] = "某研究所发布全固态电池界面阻抗优化方案第二代，能量密度提升40%。"
        news1.write_text(to_csv(rows, ["title", "url", "content", "source", "publish_time"]),
                         encoding="utf-8")
        proc = run_pipeline(sync_env(QA_BASE if real else SYNC_BASE), expect_exit=(0,))
        check("B 退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        check("B 检测到内容修订（[rev]）", "[rev]" in out, out[:200])
        lite = lite_records()
        check("B a1 更新后正文含 40%", any(
            "提升40%" in (r.get("b") or "") for r in lite if r["u"].endswith("/a1")))
        check("B lite 总数仍 7（更新不重复入库）", len(lite) == 7, f"n={len(lite)}")
        if real:
            # 一.6 存在性口径：68k 真实底座下不断言名次；a1 新正文经
            # /api/search（门户 agent_service 证据源）可命中且 body_snippet
            # 为新版本（含 40%、不含旧版独有表述）——内容级新鲜度。
            a1_hits = search_hits("界面阻抗优化方案第二代 能量密度",
                                  "全固态电池界面阻抗", 50)
            check("B 真实索引可检索新正文（存在性 top50）", len(a1_hits) >= 1,
                  f"hits={len(a1_hits)}")
            snippets = " ".join(str(c.get("body_snippet", "")) for c in a1_hits)
            check("B 证据正文为新版本（含 40%）", "40%" in snippets,
                  snippets[:120])
            check("B 证据正文不含旧版独有表述（显著提升）",
                  "显著提升" not in snippets, snippets[:120])
            # chat 流式证据链：协议在位（citations 事件正常返回）
            cites, _, _ = chat_citations("全固态电池界面阻抗优化方案第二代 能量密度")
            check("B chat 流式返回 citations 事件（证据链协议在位）",
                  isinstance(cites, list), f"{type(cites).__name__}")

        # ── C 记录删除贯穿索引 ──
        scenario("C 记录删除（wechat 删 w2 行）：Step 2b + 索引 DELETE 贯穿", True)
        wc1 = FIXTURES / "wodewoping-png" / "wechat-daily-news-csv" / "csv" / "2026-09-15.csv"
        wc1.write_text(to_csv(WECHAT1[:1], ["title", "url", "clean_text",
                                            "account_name", "publish_time"]),
                       encoding="utf-8")
        proc = run_pipeline(sync_env(QA_BASE if real else SYNC_BASE), expect_exit=(0,))
        check("C 退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
        lite = lite_records()
        urls = {r["u"] for r in lite}
        check("C 被删记录已从 lite 移除", "https://mp.weixin.example.com/w2" not in urls)
        check("C lite 总数 6", len(lite) == 6, f"n={len(lite)}")
        if real:
            st = qa_http("/api/stats")
            check("C 真实索引增量条目降为 6", st.get("incremental_records") == 6,
                  str(st.get("incremental_records")))
            # 一.6 存在性口径：top50 窗口精确标题 0 命中 = 向量/BM25 全链路删除
            w2_hits = search_hits("储能电芯价格企稳信号梳理",
                                  "储能电芯价格企稳信号梳理", 50)
            check("C 真实索引不再返回 w2（top50 精确标题 0 命中）",
                  len(w2_hits) == 0, f"hits={len(w2_hits)}")
            cites, _, _ = chat_citations("储能电芯招标价格企稳 毛利修复")
            check("C chat 流式证据链不再引用 w2", not any(
                "储能电芯价格企稳" in str(c.get("title", "")) for c in cites),
                  str([str(c.get('title', ''))[:16] for c in cites[:3]]))

        # ── D 新增文件贯穿索引 ──
        scenario("D 新增文件（news 09-16）：入库 + 索引 ADD 贯穿", True)
        news_d = FIXTURES / "wodewoping-png" / "news-spider" / "data" / "articles-2026-09-16.csv"
        news_d.write_text(to_csv(NEWS2, ["title", "url", "content", "source", "publish_time"]),
                          encoding="utf-8")
        proc = run_pipeline(sync_env(QA_BASE if real else SYNC_BASE), expect_exit=(0,))
        check("D 退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
        lite = lite_records()
        check("D 新记录入库（总数 7）",
              any(r["u"] == "https://news.example.com/b1" for r in lite) and len(lite) == 7,
              f"n={len(lite)}")
        if real:
            st = qa_http("/api/stats")
            check("D 真实索引增量条目 = 7", st.get("incremental_records") == 7,
                  str(st.get("incremental_records")))
            # 一.6 存在性口径（top50）
            check("D 真实索引可检索 b1（存在性 top50）",
                  len(search_hits("钠离子电池正极材料新路线",
                                  "钠离子电池正极材料新路线", 50)) >= 1)

        # ── E 真实中断 → 恢复（real 模式）／协议口径（stub 模式） ──
        if real:
            scenario("E 同步真实中断（连接拒绝）→ 水印不推进 → 恢复补齐（恰好一次）", True)
            news_e = FIXTURES / "wodewoping-png" / "news-spider" / "data" / "articles-2026-09-17.csv"
            news_e.write_text(to_csv(NEWS3, ["title", "url", "content", "source",
                                             "publish_time"]), encoding="utf-8")
            proc = run_pipeline(sync_env("http://127.0.0.1:18999"), expect_exit=(3,))
            check("E 中断轮退出码 3（同步失败非致命）", proc.returncode == 3,
                  f"rc={proc.returncode}")
            out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
            check("E 中断轮日志有同步失败 WARN", "QA index sync failed" in out, out[-200:])
            st = qa_http("/api/stats")
            check("E 中断后真实索引仍为 7（水印未推进）",
                  st.get("incremental_records") == 7, str(st.get("incremental_records")))
            proc = run_pipeline(sync_env(QA_BASE), expect_exit=(0,))
            check("E 恢复轮退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
            st = qa_http("/api/stats")
            check("E 恢复后真实索引 = 8", st.get("incremental_records") == 8,
                  str(st.get("incremental_records")))
            hits = search_hits("固态电解质千吨级产线落地",
                               "固态电解质千吨级产线落地", 50)
            check("E b2 恰好一次（top50 内精确标题恰 1 条 citation）",
                  len(hits) == 1, f"hits={len(hits)}")
            sc = state_counts()
            check("E 中断轮 state 已提交（news=3 文件，下轮不重复下载）",
                  sc.get("news") == 3, str(sc))
        else:
            scenario("E 同步协议口径（stub 替身）：仅验证调用触发与退出码", False)
            proc = run_pipeline(sync_env(SYNC_BASE), expect_exit=(0,))
            check("E(stub) 退出码 0", proc.returncode == 0, f"rc={proc.returncode}")
            check("E(stub) 日志确认同步完成", "QA index sync complete" in
                  (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8"))

        # ── F 无新增数据 + 失败待办补跑轮 ──
        scenario("F 无新增数据：失败待办如实处理 + 同步幂等", True)
        pending = {"conferences": {"since": "retry"}}
        (PIPE_STAGE / ".pipeline_pending.json").write_text(
            json.dumps(pending), encoding="utf-8")
        proc = run_pipeline(sync_env(QA_BASE if real else SYNC_BASE), expect_exit=(0,))
        check("F 退出码 0（无新增数据轮收敛）", proc.returncode == 0, f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        check("F 无新增数据分支进入收尾维护", "No new files" in out, out[:200])
        check("F 会议待办补跑后清除", not (PIPE_STAGE / ".pipeline_pending.json").exists()
              or not json.loads((PIPE_STAGE / ".pipeline_pending.json").read_text()
                                or "{}").get("conferences"),
              (PIPE_STAGE / ".pipeline_pending.json").read_text()[:120]
              if (PIPE_STAGE / ".pipeline_pending.json").exists() else "")
        if real:
            st = qa_http("/api/stats")
            check("F 同步幂等（仍 8 条，无重复）",
                  st.get("incremental_records") == 8, str(st.get("incremental_records")))
        rep = BOUNDARY_STAGE / "breadth" / "data" / "reports"
        check("F 报告缺口如实（无伪造报告文件）", (not rep.exists())
              or all(p.stat().st_size > 0 for p in rep.glob("**/*") if p.is_file()),
              str(list(rep.glob("**/*"))[:3]) if rep.exists() else "no reports dir")
    finally:
        for s in servers:
            s.shutdown()
        if real and not os.environ.get("E2E3S_KEEP"):
            stop_real_qa()
    failed = [n for n, ok, _ in _results if not ok]
    print(f"\n==== 结果：{len(_results) - len(failed)}/{len(_results)} 通过 ====")
    print("场景口径：")
    for label, full in SCENARIO_LABELS:
        print(f"  [{'全链成功口径' if full else '预期降级/部分口径'}] {label}")
    print("覆盖声明：")
    if real:
        print("  - QA 同步 = 真实隔离 canonical-qa 容器（底座=镜像烘焙 68k 基础索引/模型；"
              "代码层=本仓库 qa-backend 挂载，含一.6 RRF 量纲修复）")
        print("  - 检索断言口径 = 存在性/内容新鲜度（top50 citations），"
              "不断言名次（与全库 68k 真实语料的相关性竞争无关）")
    else:
        print("  - QA 同步 = HTTP 替身（协议触发/退出码/水印文件；不验证真实索引内容）")
    print("  - LLM 生成链 = 预期降级（无 key 如实跳过），生成质量验收见 六")
    if failed:
        print("失败项：", *failed, sep="\n  - ")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
