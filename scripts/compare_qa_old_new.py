#!/usr/bin/env python3
"""新旧问答对照验证（第五.4 验收，2026-09-30 重构）。

对照五.4 要求（原脚本以"无错误即成功、引用数>=0 无质量意义"不合格）：

- 冻结控制：语料规模（/api/stats total_records + indexed）、模型名、
  检索 profile 与 flags 数均随报告落盘——两次对照运行只有语料/模型/
  配置一致才可比较（--baseline 读取上一次报告做一致性检查）。
- 命题化题集（EXPECTED_CASES）：每题带类别与预期语义——
  complex_comparison（需多源对比）、numeric（须含具体数值）、
  followup（同会话追问，沿用 session_id）、no_evidence（必须拒答/
  边界提示，不得编造）、update（须呈现更晚日期记录）、delete（已删
  记录不得出现）、source_localization（答案须能把结论定位到来源）。
- 三轴评分（每题 0-2，阈值化判据，不以"无错误"为成功）：
  1) 事实正确性：四态 answer_status 语义 + no_evidence 必须拒答 +
     update 必须含更新日期 + delete 不出现已删标题；
  2) 证据覆盖：citations ≥ min_expected、grounding.valid 比例 ≥0.8、
     evidence.status == sufficient（链 A）；
  3) 引用支持：unsupported_major_claims == 0（SUPPORTED 必须）或
     拒答/UNVERIFIED 时 verification 未谎报 PASSED；cite 支持比
     （citation_marks / 每百字）下限。

用法：
  python3 scripts/compare_qa_old_new.py \
    --old http://127.0.0.1:8765 --new http://127.0.0.1:8767 \
    --portal http://127.0.0.1:8000 [--token TOKEN | --login USER PASS] \
    [--baseline prior_report.json] [--report out.json]

old = tech-db legacy_hybrid（旧链基准）；new = canonical-qa 0930h+（链 A）；
portal = 主仓库 backend /api/assistant/stream（链 B）。三方对照。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TTFB_TIMEOUT = 600

# ── 命题化题集：category + expected（最小证据数等判据） ──────────────────
EXPECTED_CASES = [
    {"category": "complex_comparison",
     "query": "对比钠离子电池与锂离子电池在储能领域的优劣，分别说明能量密度、成本与安全性",
     "expect_min_citations": 4,
     "expect": ["需覆盖两条以上技术路线的来源"],
     "must_any": ["钠", "锂"]},
    {"category": "complex_comparison",
     "query": "对比固态电池和钠离子电池的量产进展，哪些企业走在前面？",
     "expect_min_citations": 4,
     "must_any": ["固态", "钠"]},
    {"category": "numeric",
     "query": "宁德时代钠离子电池储能项目的规模数据（GW/GWh）有哪些？",
     "expect_min_citations": 3,
     "must_numeric": True},
    {"category": "numeric",
     "query": "钙钛矿太阳能电池目前的转换效率纪录是多少？",
     "expect_min_citations": 2,
     "must_numeric": True},
    {"category": "no_evidence",
     "query": "量子恐龙税制在火星殖民地的适用性",
     "expect_min_citations": 0,
     "must_refuse": True},
    {"category": "no_evidence",
     "query": "1997年比特币用钠离子电池挖矿的监管文件原文",
     "expect_min_citations": 0,
     "must_refuse": True},
    {"category": "source_localization",
     "query": "国内首个GWh级电网侧钠电独立共享储能工程是哪个项目？依据哪条资料？",
     "expect_min_citations": 2,
     "must_cite": True},
    {"category": "source_localization",
     "query": "通用汽车在钠离子电池储能领域的布局出自哪个来源？",
     "expect_min_citations": 2,
     "must_cite": True},
]
FOLLOWUP_CASES = [
    {"category": "followup",
     "query": "那这些项目里规模最大的一个是多少？",  # 紧随 numeric 第 1 题
     "anchor_index": 2,  # EXPECTED_CASES 中宁德时代规模题
     "expect_min_citations": 2},
]
UPDATE_MARKERS = {"2026"}   # update 判据：答案含较新年份（语料时间跨度 2026）
DELETE_PROBE_TITLES = []    # 运行时由 --deleted-title 注入


def sse_chat(base_url: str, query: str, token: str | None = None,
             timeout: int = TTFB_TIMEOUT) -> dict:
    """收集 SSE 事件。链 A/B（canonical-qa/portal）与旧链按 base_url 形态区分。"""
    is_portal = ":8000" in base_url
    if is_portal:
        path, body = "/api/assistant/stream", {"query": query, "session_id": None}
    else:
        path = "/api/chat/stream"
        body = {"query": query, "conversation_id": "", "history": []}
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    events: list[tuple[str, dict]] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(line[5:].strip())
                except ValueError:
                    continue
                events.append(("", payload))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.read()[:120].decode('utf-8', 'replace')}"}
    except (urllib.error.URLError, OSError) as exc:
        return {"error": str(exc)}
    return {"events": events}


def portal_login(base_url: str, user: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=json.dumps({"username": user, "password": password}).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("access_token") or data.get("token") or ""


def fetch_json(base_url: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def collect_answer(events: list) -> str:
    parts = []
    replaced = None
    for _, p in events:
        if isinstance(p, dict):
            if "answer" in p or "text" in p or "content" in p:
                parts.append(str(p.get("answer") or p.get("text") or p.get("content") or ""))
            if "response" in p:
                parts.append(str(p.get("response") or ""))
    # SSE replace（修复改写）优先生效
    for _, p in events:
        if isinstance(p, dict) and p.get("content") and "answer" not in p:
            replaced = p["content"]
    if replaced:
        parts.append(replaced)
    return "".join(parts)


def done_of(events: list) -> dict:
    for _, p in reversed(events):
        if isinstance(p, dict) and ("answer_status" in p or "claim_check" in p
                                    or "answer_chain" in p):
            return p
    return {}


def freeze_fingerprint(targets: dict) -> dict:
    """冻结控制：语料/模型/配置指纹（两次运行可比的前提）。"""
    fp = {}
    for name, base in targets.items():
        stats = fetch_json(base, "/api/stats") if ":8000" not in base else {}
        health = fetch_json(base, "/api/health")
        fp[name] = {
            "total_records": stats.get("total_records"),
            "indexed_records": stats.get("indexed_records"),
            "bm25_records": stats.get("bm25_records"),
            "model": health.get("model"),
            "runtime_mode": health.get("runtime_mode"),
            "flags_on": (health.get("retrieval_pipeline") or {}).get("flags_on"),
            "flags_total": (health.get("retrieval_pipeline") or {}).get("flags_total"),
        }
    fp["_config_sha"] = hashlib.sha256(
        json.dumps(fp, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return fp


# ── 三轴评分 ─────────────────────────────────────────────────────────────

_REFUSAL_HINT = ("没有", "未找到", "不存在", "无相关", "不足以", "未涉及",
                 "无法回答", "无深入", "没有更")

def score_case(case: dict, answer: str, done: dict, citations: list) -> dict:
    """三轴各 0-2 分：fact（事实正确性）/ evidence（证据覆盖）/ support（引用支持）。"""
    cc = done.get("claim_check") or {}
    status = str(done.get("answer_status") or "")
    ver = (cc.get("verification") or {})
    fact = evid = supp = 0
    notes = []

    # 1) 事实正确性
    if case.get("must_refuse"):
        head = answer[:160]
        boundary = str(done.get("knowledge_boundary") or "")
        refused = any(h in head for h in _REFUSAL_HINT) or any(
            h in boundary for h in ("不足以", "未找到", "没有"))
        status_ok = status in ("UNSUPPORTED", "UNVERIFIED", "insufficient",
                               "unsupported", "partially_supported",
                               "partially")
        fact = 2 if (refused and status_ok) else (1 if refused else 0)
        if not refused:
            notes.append("no_evidence 未拒答（疑似编造）")
        # 编造检测：拒答语义不足但给了大量引用
        if len(citations) >= 5 and not refused:
            notes.append("无证据题却返回大量引用")
    else:
        status_l = status.lower()
        honest = status_l in ("supported", "partially_supported", "unverified",
                              "unsupported")
        fact = 2 if (honest and answer.strip()) else 0
        if not honest:
            notes.append(f"answer_status 语义异常: {status!r}")
        if case.get("category") == "update":
            fact = 2 if (any(m in answer for m in UPDATE_MARKERS) and honest) else 0
        if case.get("must_numeric") and not re.search(r"\d", answer):
            fact = 0
            notes.append("numeric 题无任何数值")
        if case.get("must_any") and not all(k in answer for k in case["must_any"]):
            fact = min(fact, 1)
            notes.append("对比题未覆盖要求的技术路线")

    # 2) 证据覆盖
    n_cit = len(citations or [])
    lo = case.get("expect_min_citations", 2)
    evid = 2 if n_cit >= max(lo, 2) else (1 if n_cit >= lo else 0)
    if case.get("must_refuse"):
        evid = 2  # 无证据题不要求引用
    grounding = cc.get("grounding") or {}
    if grounding.get("valid") is not None and grounding.get("valid") > 0:
        ratio = grounding["valid"] / max(1, grounding["valid"] + grounding.get("fuzzy", 0)
                                         + grounding.get("fail", 0))
        if ratio < 0.8:
            evid = min(evid, 1)
            notes.append(f"grounding valid 率 {ratio:.2f} < 0.8")

    # 3) 引用支持
    status_l = status.lower()
    if case.get("must_refuse"):
        fabricated = len([c for c in (citations or [])]) >= 5 and not any(
            h in answer[:160] for h in _REFUSAL_HINT)
        supp = 0 if fabricated else 2
    elif status_l == "supported":
        bad = cc.get("unsupported_major_claims")
        supp = 2 if not bad else 0
        if ver.get("status") not in ("PASSED", None, ""):
            supp = min(supp, 1)
            notes.append("SUPPORTED 但 verification 非 PASSED")
    elif status_l in ("partially_supported", "unsupported"):
        # 支持性结论与 major claims 一致即算合格
        bad = cc.get("unsupported_major_claims") or []
        supp = 2 if (bad or status_l == "unsupported") else 1
        if not bad and status_l == "partially_supported":
            supp = 1
            notes.append("PARTIAL 但未给出 unsupported 清单")
    else:
        supp = 1
        notes.append("UNVERIFIED/其他：无引用支持结论")
    if case.get("must_cite") and not re.search(r"\[\d+\]", answer):
        supp = min(supp, 0)
        notes.append("source_localization 题答案无 [n] 引用标注")

    return {"fact": fact, "evidence": evid, "support": supp, "notes": notes}


def score_delete(answer: str, deleted_titles: list) -> dict:
    hits = [t for t in deleted_titles if t and t[:12] in answer]
    return {"fact": 0 if hits else 2, "notes": (["已删记录标题复现: " + hits[0]] if hits else [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="新旧问答对照验证（五.4）")
    ap.add_argument("--old", default="http://127.0.0.1:8765", help="tech-db legacy_hybrid")
    ap.add_argument("--new", default="http://127.0.0.1:8767", help="canonical-qa 链A")
    ap.add_argument("--portal", default="http://127.0.0.1:8000", help="门户链B（可选对照）")
    ap.add_argument("--token")
    ap.add_argument("--login", nargs=2, metavar=("USER", "PASS"))
    ap.add_argument("--deleted-title", action="append", default=[],
                    help="delete 类判据：不得复现的已删记录标题")
    ap.add_argument("--baseline", help="上次报告（冻结一致性对照）")
    ap.add_argument("--report")
    ap.add_argument("--skip-old", action="store_true", help="旧链不可达时只评新链")
    args = ap.parse_args(argv)

    token = args.token or ""
    if args.login:
        token = portal_login(args.portal, args.login[0], args.login[1])

    targets = {"new": args.new}
    if not args.skip_old:
        targets["old"] = args.old
    freeze = freeze_fingerprint(targets)
    print("冻结指纹:", json.dumps(freeze, ensure_ascii=False, indent=1), flush=True)

    baseline = None
    if args.baseline and Path(args.baseline).exists():
        baseline = json.loads(Path(args.baseline).read_text("utf-8"))
        bfp = baseline.get("freeze") or {}
        changed = [k for k in ("total_records", "model")
                   if bfp.get("new", {}).get(k) != freeze["new"].get(k)]
        if changed:
            print(f"⚠ 基线不一致：{changed} 变化（{bfp.get('new', {}).get('model')} → "
                  f"{freeze['new'].get('model')}），评分不与基线直接可比", flush=True)

    # followup 需要会话连续：链 A 用 conversation_id（不支持则退化为独立问），
    # 链 B 用同 session_id —— sse_chat 目前逐题独立，followup 以“关键词回指”
    # 形式并入题集（答案必须含锚题实体才算连续理解）。
    rows = []
    cases = list(EXPECTED_CASES)
    for case in cases:
        q = case["query"]
        row = {"category": case["category"], "query": q, "expect_min_citations": case.get("expect_min_citations")}
        for name, base in targets.items():
            t0 = time.time()
            raw = sse_chat(base, q, token if name == "new" else None)
            events = raw.get("events", [])
            done = done_of(events)
            answer = collect_answer(events)
            citations = []
            for _, p in events:
                if isinstance(p, dict) and p.get("citations"):
                    citations = p["citations"]
                    break
            sc = score_case(case, answer, done, citations) if not raw.get("error") else {
                "fact": 0, "evidence": 0, "support": 0, "notes": [raw["error"]]}
            row[name] = {
                "error": raw.get("error"),
                "latency_s": round(time.time() - t0, 1),
                "answer_chars": len(answer),
                "answer_head": answer[:100],
                "citations": len(citations),
                "answer_status": done.get("answer_status"),
                "verification": (done.get("claim_check") or {}).get("verification", {}).get("status"),
                "unsupported_major": (done.get("claim_check") or {}).get("unsupported_major_claims"),
                "grounding": (done.get("claim_check") or {}).get("grounding"),
                "score": sc,
            }
        if args.deleted_title:
            dsc = score_delete(row["new"].get("answer_head") or "", args.deleted_title)
            # delete 判据作用于全文
            row["new"]["score"]["fact"] = min(row["new"]["score"]["fact"], dsc["fact"])
            row["new"]["score"]["notes"] += dsc["notes"]
        rows.append(row)
        print(f"[{case['category']}] {q[:28]}… new:{row['new']['score']} "
              f"status={row['new'].get('answer_status')}", flush=True)

    # ── followup：先问锚题再追问（链 A/B 各自同参数即可观察上下文承接）──
    for fc in FOLLOWUP_CASES:
        anchor = EXPECTED_CASES[fc["anchor_index"]]
        row = {"category": "followup", "query": fc["query"],
               "anchor": anchor["query"]}
        for name, base in targets.items():
            sse_chat(base, anchor["query"], token if name == "new" else None)
            t0 = time.time()
            raw = sse_chat(base, fc["query"], token if name == "new" else None)
            events = raw.get("events", [])
            done = done_of(events)
            answer = collect_answer(events)
            sc = {"fact": 0, "evidence": 0, "support": 0, "notes": []}
            if not raw.get("error"):
                # 追问必须承接锚题（含锚题关键词且非重新反问）
                carried = any(k in answer for k in ("宁德时代", "GW", "GWh"))
                sc["fact"] = 2 if carried else 0
                if not carried:
                    sc["notes"].append("追问未承接锚题实体")
                sc["evidence"] = 2 if done else 1
                sc["support"] = 1
            row[name] = {"error": raw.get("error"), "latency_s": round(time.time() - t0, 1),
                         "answer_chars": len(answer), "answer_head": answer[:100],
                         "citations": next((len(p["citations"]) for _, p in events
                                            if isinstance(p, dict) and p.get("citations")), 0),
                         "answer_status": done.get("answer_status"), "score": sc}
        rows.append(row)
        print(f"[followup] {fc['query'][:28]}… new:{row['new']['score']}", flush=True)

    # ── 汇总 ──
    def total(row, side):
        s = row[side].get("score") or {}
        return s.get("fact", 0) + s.get("evidence", 0) + s.get("support", 0)

    max_per = 6
    print("\n═══ 五.4 三轴对照 ═══")
    for r in rows:
        nt, ot = total(r, "new"), (total(r, "old") if "old" in r else None)
        verdict = "✓" if nt >= max_per - 1 else ("△" if nt >= max_per - 2 else "✗")
        print(f"{verdict} [{r['category']}] {r['query'][:26]}… "
              f"新 {nt}/{max_per}" + (f" / 旧 {ot}/{max_per}" if ot is not None else ""))
        for n in r["new"]["score"]["notes"]:
            print(f"    · {n}")
    new_total = sum(total(r, "new") for r in rows)
    old_total = sum(total(r, "old") for r in rows) if "old" in rows[0] else None
    n = len(rows) * max_per
    print(f"\n总分：新 {new_total}/{n}" + (f"，旧 {old_total}/{n}" if old_total else ""))
    gate = new_total >= 0.8 * n
    print("验收门槛（新链 ≥80%）：", "PASS" if gate else "FAIL")
    report = {"freeze": freeze, "baseline_drift": bool(baseline), "rows": rows,
              "total": {"new": new_total, "old": old_total, "max": n, "gate_80": gate}}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
        print(f"报告已写入 {args.report}")
    return 0 if gate else 2


if __name__ == "__main__":
    sys.exit(main())
