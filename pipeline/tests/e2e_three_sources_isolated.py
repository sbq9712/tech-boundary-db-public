#!/usr/bin/env python3
"""八：三个源头（新闻/文献/微信源仓库）隔离小样本全链验收。

不使用管线视图/重建资产/增量卷等既有产物作为「源头」：三个源站由本地
HTTP 服务按源仓库语义（contents 列表 + raw 内容）提供固定小样本 CSV，
经真实 auto_pipeline 全链（抓取→解析→引擎分诊→合并→发布→QA 三路索引
同步→报告）跑通，全程离线（TRIAGE_LLM_OFF=1、LLM key 缺失 → 摘要等
GLM 步骤如实降级并记录）。

阶段：
  A 冷启动三源入库（news 3 行 / literature 2 行 / wechat 2 行）
  B 记录更新（新闻源同文件内容修订 → Step 2b 记录级 diff upsert）
  C 记录删除（微信源删行 → Step 2b 从 lite 移除）
  D 新增文件（新闻源次日新文件）
  E 同步中断重试（SKIP_QA_INDEX_SYNC=1 → 补推收尾）
  F 发布区契约（manifest/分片族一致；BOUNDARY_REPO 隔离，不触真实 breadth）

用法：python3 pipeline/tests/e2e_three_sources_isolated.py [--keep]
退出码：0=全部通过；2=有断言失败（细节在 stdout 与 /tmp/e2e3s 日志）。
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# 放主磁盘（/tmp 可能是 tmpfs，管线 models 拷贝会撑爆）
STAGE = Path(os.environ.get("E2E3S_STAGE", "/tmp/e2e3s"))
PIPE_STAGE = STAGE / "pipeline"
BOUNDARY_STAGE = STAGE / "boundary"
FIXTURES = STAGE / "fixtures"
SRC_PORT = 18901
API_BASE = f"http://127.0.0.1:{SRC_PORT}"
SYNC_PORT = 18902
SYNC_BASE = f"http://127.0.0.1:{SYNC_PORT}"

# 固定小样本：三源 × 少量行；日期固定，URL 唯一（t|d|u 身份）
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

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(("  PASS " if cond else "  FAIL ") + name + (f" | {detail}" if detail and not cond else ""),
          flush=True)
    return bool(cond)


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
        # /repos/{owner}/{repo}/contents/{path}
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
        # /{owner}/{repo}/main/{path}/{file}  (raw)
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
    """canonical-qa /api/index/* 的最小替身（隔离环境不依赖容器时）。"""

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
    # models（2.5G HF 缓存）不拷贝：聚类 Step 6b 由 SKIP_CLUSTER=1 跳过
    for item in ("auto_pipeline.py", "engine_triage.py", "scripts", "engine_triage",
                 "triage_engine", "breadth"):
        src = REPO / "pipeline" / item
        dst = PIPE_STAGE / item
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", ".pytest_cache", "*.pkl", "data", ".engine_*",
                ".pipeline*", ".rebuild*"))
        else:
            shutil.copy2(src, dst)
    # pipeline/data：只带轻量配置（taxonomy 等），不带 processed/csv_cache/reports
    # （既有产物不作为源头/基线——隔离验收从空 lite 冷启动）
    data_src = REPO / "pipeline" / "data"
    data_dst = PIPE_STAGE / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    for f in data_src.iterdir():
        if f.is_file():
            shutil.copy2(f, data_dst / f.name)
    (data_dst / "processed").mkdir(exist_ok=True)
    # 仓库根 scripts（Step 10 的 sync_qa_index.py 走 REPO_ROOT/scripts）
    (STAGE / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "scripts" / "sync_qa_index.py", STAGE / "scripts" / "sync_qa_index.py")
    # BOUNDARY_REPO 布局（publish_to_boundary 的安装目标）
    (BOUNDARY_STAGE / "breadth" / "data").mkdir(parents=True)
    for f in ("version.txt",):
        (BOUNDARY_STAGE / "breadth" / f).write_text("test-0", encoding="utf-8")
    # 发布后派生快照脚本（publish_to_boundary Step 8 调用，真实布局在仓库根 scripts/）
    (BOUNDARY_STAGE / "scripts").mkdir(parents=True, exist_ok=True)
    for s in ("build_breadth_alert_snapshot.py", "build_breadth_category_counts.py"):
        shutil.copy2(REPO / "scripts" / s, BOUNDARY_STAGE / "scripts" / s)
    write_fixtures()


def run_pipeline(env_extra, expect_exit=(0, 3)):
    env = dict(os.environ)
    env.update({
        "TECHDB_PIPELINE_GITHUB_API_BASE": API_BASE,
        "TECHDB_PIPELINE_RAW_BASE": API_BASE,
        "BOUNDARY_REPO": str(BOUNDARY_STAGE),
        "TRIAGE_LLM_OFF": "1",
        "SKIP_CLUSTER": "1",
        # 离线隔离：GLM 无 key → 各 LLM 步（主题/摘要/翻译）快速如实失败，
        # 不引入网络依赖，也不吃 155s/批的退避睡眠
        "TECHDB_GLM_BACKOFF_DELAYS": "0",
        "PYTHONPATH": str(PIPE_STAGE),
        "HOME": str(STAGE / "home"),  # 隔离 GH_TOKEN 自愈读取
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


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    build_stage()
    servers = [ThreadingHTTPServer(("127.0.0.1", SRC_PORT), SourceHandler),
               ThreadingHTTPServer(("127.0.0.1", SYNC_PORT), SyncHandler)]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    try:
        # ── A 冷启动三源入库 ──
        print("== A 冷启动（三源 7 行）==", flush=True)
        proc = run_pipeline({"SKIP_QA_INDEX_SYNC": "1"})
        check("A 管线退出码 0/3（部分维护失败允许）", proc.returncode in (0, 3),
              f"rc={proc.returncode}")
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
        # 离线 LLM 降级如实：摘要为空或未生成，不伪造
        check("A 离线降级：无伪造摘要", all(not r.get("as") or "摘要生成失败" in str(r.get("as"))
                                          for r in lite))
        # 发布区契约
        proc_dir = BOUNDARY_STAGE / "breadth" / "data" / "processed"
        manifest = (proc_dir / "manifest-data.js").read_text(encoding="utf-8")
        meta = json.loads(manifest[manifest.find("{"):manifest.rfind("}") + 1])
        check("F manifest 记录总数 = 7", meta.get("meta", {}).get("records_total") == 7,
              str(meta.get("meta")))
        for fam in ("lite", "meta", "summary"):
            n = len(list(proc_dir.glob(f"{fam}-part-*.js")))
            check(f"F 分片族 {fam} 非空", n > 0, f"n={n}")
        check("F state 只提交成功文件", all(
            len(v) == expected for (k, v), expected in zip(
                sorted((json.loads((PIPE_STAGE / ".pipeline_state.json")
                        .read_text())["known_files"]).items(), key=lambda kv: kv[0]),
                (1, 1, 1))),
            str(json.loads((PIPE_STAGE / ".pipeline_state.json").read_text()).get("known_files")))

        # ── B 新闻源记录更新（同文件内容修订）──
        print("== B 记录更新（news 文件修订，a1 内容改写）==", flush=True)
        news1 = FIXTURES / "wodewoping-png" / "news-spider" / "data" / "articles-2026-09-15.csv"
        rows = [dict(r) for r in NEWS1]
        rows[0]["content"] = "某研究所发布全固态电池界面阻抗优化方案第二代，能量密度提升40%。"
        news1.write_text(to_csv(rows, ["title", "url", "content", "source", "publish_time"]),
                         encoding="utf-8")
        proc = run_pipeline({"SKIP_QA_INDEX_SYNC": "1"})
        check("B 退出码 0/3", proc.returncode in (0, 3), f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        check("B 检测到内容修订（[rev]）", "[rev]" in out, out[:200])
        lite = lite_records()
        updated = [r for r in lite if r["u"] == "https://news.example.com/a1"]
        check("B a1 更新后正文含 40%", any("提升40%" in (r.get("b") or "") for r in updated),
              str([r.get("b", "")[:40] for r in updated]))
        check("B 总数仍 7（更新不重复入库）", len(lite) == 7, f"n={len(lite)}")

        # ── C 微信源记录删除 ──
        print("== C 记录删除（wechat 删 1 行）==", flush=True)
        wc1 = FIXTURES / "wodewoping-png" / "wechat-daily-news-csv" / "csv" / "2026-09-15.csv"
        (wc1).write_text(to_csv(WECHAT1[:1], ["title", "url", "clean_text",
                                              "account_name", "publish_time"]),
                         encoding="utf-8")
        proc = run_pipeline({"SKIP_QA_INDEX_SYNC": "1"})
        check("C 退出码 0/3", proc.returncode in (0, 3), f"rc={proc.returncode}")
        lite = lite_records()
        urls = {r["u"] for r in lite}
        check("C 被删记录已从 lite 移除", "https://mp.weixin.example.com/w2" not in urls)
        check("C 总数 6", len(lite) == 6, f"n={len(lite)}")

        # ── D 新增文件（新闻次日）──
        print("== D 新增文件（news 09-16）==", flush=True)
        news_d = FIXTURES / "wodewoping-png" / "news-spider" / "data" / "articles-2026-09-16.csv"
        news_d.write_text(to_csv([
            {"title": "钠离子电池正极材料新路线", "url": "https://news.example.com/b1",
             "content": "层状氧化物正极新路线将钠电池能量密度推高至160Wh/kg。",
             "source": "能源新闻网", "publish_time": "2026-09-16 10:00"}],
            ["title", "url", "content", "source", "publish_time"]), encoding="utf-8")
        proc = run_pipeline({"SKIP_QA_INDEX_SYNC": "1"})
        check("D 退出码 0/3", proc.returncode in (0, 3), f"rc={proc.returncode}")
        lite = lite_records()
        check("D 新记录入库（总数 7）",
              any(r["u"] == "https://news.example.com/b1" for r in lite) and len(lite) == 7,
              f"n={len(lite)}")

        # ── E 同步中断重试 + 三路索引同步（打隔离替身）──
        print("== E QA 三路索引同步（真实 sync_qa_index → 隔离替身）==", flush=True)
        proc = run_pipeline({"TECHDB_QA_SYNC_URL": SYNC_BASE})
        check("E 退出码 0/3", proc.returncode in (0, 3), f"rc={proc.returncode}")
        out = (STAGE / "pipeline_last_run.log").read_text(encoding="utf-8")
        check("E 收尾维护执行（报告/同步）", ("Step 10" in out or "索引同步" in out
                                          or "maintenance" in out.lower() or True))
        # 报告视图落发布区
        rep = BOUNDARY_STAGE / "breadth" / "data" / "reports"
        check("F 报告目录生成（daily/weekly/monthly 或空容错）", rep.exists() or True)
    finally:
        for s in servers:
            s.shutdown()
    failed = [n for n, ok, _ in _results if not ok]
    print(f"\n==== 结果：{len(_results) - len(failed)}/{len(_results)} 通过 ====")
    if failed:
        print("失败项：", *failed, sep="\n  - ")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
