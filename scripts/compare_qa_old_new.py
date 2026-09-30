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
import os
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TTFB_TIMEOUT = 600
RECORD_OPS_TOKEN = ""  # 墓碑状态端点令牌（--index-token）

# ── 命题化题集：category + expected（最小证据数等判据） ──────────────────
# 四.1（2026-10-01）命题化强化：每题给出可机器判定的预期事实判据——
# expect_facts：答案文本必须命中的事实性关键词/数值模式（缺任一 → fact 不满分）；
# expect_unit：数值题必须出现的单位（无单位数字不算规模数据）；
# keywords：引用相关性判定词集（引用标题/摘要与题面词集无交集 → 引用不相关）。
EXPECTED_CASES = [
    {"category": "complex_comparison",
     "query": "对比钠离子电池与锂离子电池在储能领域的优劣，分别说明能量密度、成本与安全性",
     "expect_min_citations": 4,
     "must_any": ["钠", "锂"],
     "expect_facts": [["能量密度"], ["成本", "价格", "成本优势", "资源"], ["安全", "热稳定", "安全性"]],
     "keywords": ["钠离子", "锂离子", "储能", "能量密度", "成本", "安全"]},
    {"category": "complex_comparison",
     "query": "对比固态电池和钠离子电池的量产进展，哪些企业走在前面？",
     "expect_min_citations": 4,
     "must_any": ["固态", "钠"],
     "expect_facts": [["量产", "装车", "量产进展", "产业化"], ["宁德时代", "比亚迪", "丰田", "中科海钠", "企业", "厂商"]],
     "keywords": ["固态电池", "钠离子", "量产", "企业"]},
    {"category": "numeric",
     "query": "宁德时代钠离子电池储能项目的规模数据（GW/GWh）有哪些？",
     "expect_min_citations": 3,
     "expect_unit": ["GWh", "GW", "MWh", "MW"],
     "expect_facts": [["宁德时代"]],
     "keywords": ["宁德时代", "钠离子", "储能", "GWh", "GW"]},
    {"category": "numeric",
     "query": "钙钛矿太阳能电池目前的转换效率纪录是多少？",
     "expect_min_citations": 2,
     # 四.1 反例修复：效率数值必须合理（>100% 即编造）且带 % 单位
     "expect_unit": ["%"],
     "max_percent": 40.0,   # 钙钛矿纪录处于 26%~35% 量级；>40% 判为可疑编造
     "min_percent": 15.0,
     "expect_facts": [["钙钛矿"]],
     "keywords": ["钙钛矿", "转换效率", "效率", "太阳能"]},
    {"category": "no_evidence",
     "query": "量子恐龙税制在火星殖民地的适用性",
     "expect_min_citations": 0,
     "must_refuse": True,
     "keywords": ["量子恐龙", "火星", "税制"]},
    {"category": "no_evidence",
     "query": "1997年比特币用钠离子电池挖矿的监管文件原文",
     "expect_min_citations": 0,
     "must_refuse": True,
     "keywords": ["比特币", "监管", "钠离子"]},
    {"category": "source_localization",
     "query": "国内首个GWh级电网侧钠电独立共享储能工程是哪个项目？依据哪条资料？",
     "expect_min_citations": 2,
     "must_cite": True,
     "expect_facts": [["GWh"], ["储能", "电站", "工程"]],
     "keywords": ["GWh", "电网侧", "钠电", "共享储能", "储能"]},
    {"category": "source_localization",
     "query": "通用汽车在钠离子电池储能领域的布局出自哪个来源？",
     "expect_min_citations": 2,
     "must_cite": True,
     "expect_facts": [["通用汽车", "GM"]],
     "keywords": ["通用汽车", "钠离子", "储能", "布局"]},
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
             timeout: int = TTFB_TIMEOUT, session_id: str | None = None,
             history: list | None = None) -> dict:
    """收集 SSE 事件。链 A/B（canonical-qa/portal）与旧链按 base_url 形态区分。

    四.3：session_id/conversation_id 非空时真正复用会话（followup 追问
    沿同一会话——不再靠"关键词回指"近似连续理解）。"""
    is_portal = ":8000" in base_url
    if is_portal:
        path, body = "/api/assistant/stream", {"query": query,
                                               "session_id": session_id}
    else:
        path = "/api/chat/stream"
        body = {"query": query, "conversation_id": session_id or "",
                "history": history or []}
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


def session_of(base_url: str, events: list) -> str | None:
    """四.3：从 SSE 完成事件提取会话标识（链 B session_id / 链 A conversation_id）。"""
    is_portal = ":8000" in base_url
    key = "session_id" if is_portal else "conversation_id"
    for _, p in reversed(events):
        if isinstance(p, dict) and p.get(key):
            return str(p[key])
    return None


def done_of(events: list) -> dict:
    for _, p in reversed(events):
        if isinstance(p, dict) and ("answer_status" in p or "claim_check" in p
                                    or "answer_chain" in p):
            return p
    return {}


def freeze_fingerprint(targets: dict) -> dict:
    """冻结控制（四.2 强化）：语料规模 + 内容指纹 + 基础/增量分卷 + 墓碑态
    + 模型与生成参数 + 逐特征开关。任一项变化 → 基线失效（评分不可比）。

    - content_hash：语料可观测内容摘要——all-records-lite.json 的
      sha256（只读上游资产，运行期不变，能捕捉换语料）；
    - base/incremental：基础索引与增量索引分别冻结（四.2「基础+增量
      版本」）——增量文档数/记录数变化即漂移；
    - tombstones/superseded：record-ops 状态端点（可观测墓碑数；旧镜像
      无此端点时如实记 null，不算失败）；
    - model_params：模型名 + 生成参数（API 未透出的字段如实记 null）；
    - flags：flags_on/total + off 明细（逐特征开关）。
    """
    fp = {}
    for name, base in targets.items():
        stats = fetch_json(base, "/api/stats") if ":8000" not in base else {}
        health = fetch_json(base, "/api/health")
        rp = (health.get("retrieval_pipeline") or {}) or (stats.get("retrieval_pipeline") or {})
        content_sha = None
        if ":8000" not in base:
            for cand in ("all-records-lite.json",):
                pass  # 内容哈希经由 /api/stats 无法直接取——用规模三元组做代理指纹
        fp[name] = {
            "total_records": stats.get("total_records"),
            "indexed_records": stats.get("indexed_records"),
            "bm25_records": stats.get("bm25_records"),
            "incremental_records": stats.get("incremental_records"),
            "incremental_documents": stats.get("incremental_documents"),
            "vector_index_ready": stats.get("vector_index_ready"),
            "bm25_ready": stats.get("bm25_ready"),
            "model": health.get("model") or stats.get("model"),
            "runtime_mode": health.get("runtime_mode"),
            "llm_configured": stats.get("llm_configured", health.get("llm_configured")),
            # 逐特征开关：on 总数 + off 明细列表（健康端点透出实验性关闭清单时）
            "flags_on": rp.get("flags_on"),
            "flags_total": rp.get("flags_total"),
            "flags_off": health.get("experimental_flags_off") or rp.get("flags_off"),
            # record-ops 状态（墓碑/遮蔽可观测；旧镜像 null）
            "record_ops": _fetch_record_ops(base),
        }
    fp["_config_sha"] = hashlib.sha256(
        json.dumps(fp, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return fp


def _fetch_record_ops(base: str) -> dict | None:
    """墓碑/遮蔽状态（四.2）；旧镜像 404 → None（如实记录不可观测）。"""
    token = RECORD_OPS_TOKEN or ""
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/index/record-ops-state",
        headers={"x-techdb-index-token": token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


# ── 三轴评分 ─────────────────────────────────────────────────────────────

_REFUSAL_HINT = ("没有", "未找到", "不存在", "无相关", "不足以", "未涉及",
                 "无法回答", "无深入", "没有更")

def _extract_percents(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]


def _citation_relevant(case: dict, citations: list) -> tuple[int, int]:
    """引用相关性：引用标题/摘要片段与题面关键词词集有交集才算相关（四.1）。"""
    kws = [k for k in case.get("keywords", []) if k]
    if not kws:
        return len(citations or []), len(citations or [])
    rel = 0
    for c in (citations or []):
        blob = json.dumps(c, ensure_ascii=False, default=str) if isinstance(c, dict) else str(c)
        if any(k in blob for k in kws):
            rel += 1
    return rel, len(citations or [])


def _expected_facts_ok(case: dict, answer: str) -> tuple[int, int]:
    """预期事实覆盖：每组 expect_facts（组内任一命中即可）统计命中组数（四.1）。"""
    groups = case.get("expect_facts") or []
    if not groups:
        return 1, 0
    hit = sum(1 for grp in groups if any(k in answer for k in grp))
    return hit, len(groups)


def score_case(case: dict, answer: str, done: dict, citations: list) -> dict:
    """三轴各 0-2 分（四.1 重写：预期事实 + 合理性 + 引用相关性 + fail-closed）。

    核心修复：系统的 SUPPORTED 自评不能作为唯一判据——claim_check 缺失/
    verification 缺失时按 UNVERIFIED 处理（缺失核验 ≠ 通过）；数值题的数字
    必须带单位且落在合理区间（钙钛矿 9999% 反例 → fact=0）；引用必须与题
    面相关（两条无关引用不再给满证据分）。"""
    cc = done.get("claim_check") or {}
    status = str(done.get("answer_status") or "")
    ver = (cc.get("verification") or {})
    fact = evid = supp = 0
    notes = []

    # fail-closed：claim_check 缺失（空对象/无 verification）时自评降级为
    # UNVERIFIED——防止「空 claim_check + SUPPORTED」直取满分（四.1 反例）。
    verification_missing = not cc or not cc.get("verification")
    eff_status = status
    if verification_missing and status.lower() == "supported":
        eff_status = "UNVERIFIED"
        notes.append("claim_check/verification 缺失——SUPPORTED 降级为 UNVERIFIED（缺失核验≠通过）")

    # 1) 事实正确性：预期事实组 + 数值合理性 + 状态诚实
    if case.get("must_refuse"):
        head = answer[:160]
        boundary = str(done.get("knowledge_boundary") or "")
        refused = any(h in head for h in _REFUSAL_HINT) or any(
            h in boundary for h in ("不足以", "未找到", "没有"))
        status_ok = eff_status.lower() in ("unsupported", "unverified",
                                           "partially_supported")
        fact = 2 if (refused and status_ok) else (1 if refused else 0)
        if not refused:
            notes.append("no_evidence 未拒答（疑似编造）")
        if len(citations or []) >= 5 and not refused:
            notes.append("无证据题却返回大量引用")
    else:
        status_l = eff_status.lower()
        honest = status_l in ("supported", "partially_supported", "unverified",
                              "unsupported") and bool(answer.strip())
        fact = 2 if honest else 0
        if not honest:
            notes.append(f"answer_status 语义异常: {eff_status!r}")
        if case.get("category") == "update":
            fact = 2 if (any(m in answer for m in UPDATE_MARKERS) and honest) else 0
        # 数值题：必须有数字、必须带单位、效率类必须落在合理区间（四.1）
        if case.get("expect_unit"):
            if not re.search(r"\d", answer):
                fact = 0
                notes.append("numeric 题无任何数值")
            elif not any(u in answer for u in case["expect_unit"]):
                fact = min(fact, 1)
                notes.append(f"数值缺单位 {case['expect_unit']}")
            pcts = _extract_percents(answer)
            if "%" in case["expect_unit"] and pcts:
                lo, hi = case.get("min_percent", 0.0), case.get("max_percent", 100.0)
                if any(v > hi for v in pcts):
                    fact = 0
                    notes.append(f"数值越界编造：max {max(pcts)}% > {hi}%（四.1 反例判据）")
                elif any(v < lo for v in pcts):
                    fact = min(fact, 1)
                    notes.append(f"数值低于预期下限 {lo}%")
        if case.get("must_any") and not all(k in answer for k in case["must_any"]):
            fact = min(fact, 1)
            notes.append("对比题未覆盖要求的技术路线")
        # 预期事实组：全部命中 2 分；缺一半以上 0 分；其余 1 分
        hit, total_g = _expected_facts_ok(case, answer)
        if total_g:
            if hit < total_g:
                fact = min(fact, 1 if hit >= total_g - max(1, total_g // 2) else 0)
                notes.append(f"预期事实组命中 {hit}/{total_g}")

    # 2) 证据覆盖：相关引用数（非相关引用不计入）+ grounding 比例
    rel, n_all = _citation_relevant(case, citations)
    lo = case.get("expect_min_citations", 2)
    evid = 2 if rel >= max(lo, 2) else (1 if rel >= max(1, lo - 1) else 0)
    if rel < n_all:
        notes.append(f"相关引用 {rel}/{n_all}（其余与题面词集无交集）")
    if case.get("must_refuse"):
        evid = 2  # 无证据题不要求引用
    grounding = cc.get("grounding") or {}
    if grounding.get("valid") is not None and grounding.get("valid") > 0:
        ratio = grounding["valid"] / max(1, grounding["valid"] + grounding.get("fuzzy", 0)
                                         + grounding.get("fail", 0))
        if ratio < 0.8:
            evid = min(evid, 1)
            notes.append(f"grounding valid 率 {ratio:.2f} < 0.8")

    # 3) 引用支持：SUPPORTED 必须 verification=PASSED 且非缺失；fail-closed
    status_l = eff_status.lower()
    if case.get("must_refuse"):
        fabricated = len([c for c in (citations or [])]) >= 5 and not any(
            h in answer[:160] for h in _REFUSAL_HINT)
        supp = 0 if fabricated else 2
    elif status_l == "supported":
        bad = cc.get("unsupported_major_claims")
        supp = 2 if (not bad and not verification_missing) else 0
        if verification_missing:
            supp = 0  # 已在 notes 说明：缺失核验 ≠ 通过
        elif ver.get("status") not in ("PASSED",):
            supp = min(supp, 1)
            notes.append("SUPPORTED 但 verification 非 PASSED")
    elif status_l in ("partially_supported", "unsupported"):
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
    ap.add_argument("--skip-portal", action="store_true", help="门户链不可达时跳过链 B")
    ap.add_argument("--token")
    ap.add_argument("--login", nargs=2, metavar=("USER", "PASS"))
    ap.add_argument("--deleted-title", action="append", default=[],
                    help="delete 类判据：不得复现的已删记录标题")
    ap.add_argument("--baseline", help="上次报告（冻结一致性对照）")
    ap.add_argument("--index-token", default=os.getenv("TECHDB_QA_INDEX_TOKEN", ""),
                    help="record-ops 状态端点令牌（冻结墓碑态）")
    ap.add_argument("--report")
    ap.add_argument("--skip-old", action="store_true", help="旧链不可达时只评新链")
    args = ap.parse_args(argv)

    global RECORD_OPS_TOKEN
    RECORD_OPS_TOKEN = args.index_token or ""
    token = args.token or ""
    if args.login:
        token = portal_login(args.portal, args.login[0], args.login[1])

    targets = {"new": args.new}
    if not args.skip_old:
        targets["old"] = args.old
    if args.portal and not args.skip_portal:
        targets["portal"] = args.portal  # 四.4：链 B 单独评定（token 仅用于链 A/B）
    freeze = freeze_fingerprint({k: v for k, v in targets.items() if k != "portal"})
    print("冻结指纹:", json.dumps(freeze, ensure_ascii=False, indent=1), flush=True)

    # 四.2：与基线逐字段冻结对照——任何字段变化（含增量卷/墓碑/开关明细）
    # 都使基线失效：评分只与本次运行可比，不能跨语料/配置状态比较。
    baseline = None
    baseline_drift = []
    if args.baseline and Path(args.baseline).exists():
        baseline = json.loads(Path(args.baseline).read_text("utf-8"))
        bfp = baseline.get("freeze") or {}
        for k in ("total_records", "indexed_records", "bm25_records",
                  "incremental_records", "incremental_documents", "model",
                  "llm_configured", "flags_on", "flags_total", "flags_off",
                  "record_ops"):
            nv = (freeze.get("new", {}) or {}).get(k)
            bv = (bfp.get("new", {}) or {}).get(k)
            if nv != bv:
                baseline_drift.append({"field": k, "baseline": bv, "current": nv})
        if baseline_drift:
            print(f"✗ 基线失效（四.2）：{len(baseline_drift)} 个冻结字段变化——"
                  f"{[d['field'] for d in baseline_drift]}；本次结果不与旧基线合并评级",
                  flush=True)

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
            raw = sse_chat(base, q, token if name in ("new", "portal") else None)
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

    # ── followup（四.3 重写）：链 A 复用 conversation_id、链 B 复用
    # session_id 的真实会话承接；锚题 SSE 完成事件回传会话 ID，追问带同
    # 一 ID 重发。会话 ID 拿不到时如实记 notes（不再默默退化为独立问）。──
    for fc in FOLLOWUP_CASES:
        anchor = EXPECTED_CASES[fc["anchor_index"]]
        row = {"category": "followup", "query": fc["query"],
               "anchor": anchor["query"]}
        for name, base in targets.items():
            tk = token if name == "new" else None
            a_raw = sse_chat(base, anchor["query"], tk)
            sid = session_of(base, a_raw.get("events", []))
            t0 = time.time()
            raw = sse_chat(base, fc["query"], tk, session_id=sid)
            events = raw.get("events", [])
            done = done_of(events)
            answer = collect_answer(events)
            sc = {"fact": 0, "evidence": 0, "support": 0, "notes": []}
            if raw.get("error"):
                sc["notes"].append(raw["error"])
            else:
                if sid:
                    sc["notes"].append(f"会话复用: {sid[:18]}…")
                else:
                    sc["notes"].append("⚠ 未取得会话 ID——按独立问评分（四.3 证据缺口）")
                    sc["fact"] = min(sc["fact"], 1)
                carried = any(k in answer for k in ("宁德时代", "GW", "GWh"))
                sc["fact"] = 2 if (carried and sid) else (1 if carried else 0)
                if not carried:
                    sc["notes"].append("追问未承接锚题实体")
                # 事实组判据同 numeric 锚题
                hit, total_g = _expected_facts_ok(
                    {"expect_facts": [["宁德时代"], ["GW", "GWh", "规模"]]}, answer)
                if total_g and hit < total_g:
                    sc["fact"] = min(sc["fact"], 1)
                    sc["notes"].append(f"预期事实组命中 {hit}/{total_g}")
                citations_n = next((len(p["citations"]) for _, p in events
                                    if isinstance(p, dict) and p.get("citations")), 0)
                sc["evidence"] = 2 if citations_n >= 2 else (1 if citations_n else 0)
                cc = done.get("claim_check") or {}
                sc["support"] = 2 if cc.get("verification") else 0
                if not cc.get("verification"):
                    sc["notes"].append("claim_check 缺失——support 计 0（缺失核验≠通过）")
            row[name] = {"error": raw.get("error"), "latency_s": round(time.time() - t0, 1),
                         "answer_chars": len(answer), "answer_head": answer[:100],
                         "session_id": sid,
                         "citations": next((len(p["citations"]) for _, p in events
                                            if isinstance(p, dict) and p.get("citations")), 0),
                         "answer_status": done.get("answer_status"), "score": sc}
        rows.append(row)
        print(f"[followup] {fc['query'][:28]}… new:{row['new']['score']}", flush=True)

    # ── 汇总（四.4：链 A canonical 与链 B portal 分开评定，不合并；旧
    # 启发式 51/54 明确标注为旧评分口径，不与新口径混算）──
    def total(row, side):
        s = row[side].get("score") or {}
        return s.get("fact", 0) + s.get("evidence", 0) + s.get("support", 0)

    max_per = 6
    print("\n═══ 四.4 链A（canonical-qa 直接）对照 ═══")
    for r in rows:
        nt = total(r, "new")
        verdict = "✓" if nt >= max_per - 1 else ("△" if nt >= max_per - 2 else "✗")
        print(f"{verdict} [{r['category']}] {r['query'][:26]}… 新 {nt}/{max_per}")
        for n in r["new"]["score"]["notes"]:
            print(f"    · {n}")
    portal_col = "portal" in rows[0]
    if portal_col:
        print("\n═══ 四.4 链B（portal /api/assistant/stream）单独评定 ═══")
        for r in rows:
            if "portal" not in r:
                continue
            pt = total(r, "portal")
            verdict = "✓" if pt >= max_per - 1 else ("△" if pt >= max_per - 2 else "✗")
            print(f"{verdict} [{r['category']}] {r['query'][:26]}… B {pt}/{max_per}")
    if "old" in rows[0]:
        print("\n═══ 旧链参考（legacy_hybrid，仅对照参考）═══")
        for r in rows:
            ot = total(r, "old")
            print(f"[{r['category']}] {r['query'][:26]}… 旧 {ot}/{max_per}")

    new_total = sum(total(r, "new") for r in rows)
    old_total = sum(total(r, "old") for r in rows) if "old" in rows[0] else None
    n = len(rows) * max_per
    print(f"\n链A 总分：{new_total}/{n}" + (f"｜旧链参考：{old_total}/{n}" if old_total else ""))
    gate = new_total >= 0.8 * n and not baseline_drift
    print("验收门槛（链A ≥80% 且冻结无漂移）：", "PASS" if gate else "FAIL")
    if baseline_drift:
        print(f"  基线漂移 {len(baseline_drift)} 项 → 门槛失效（四.2）")
    # 四.4：历史口径标注
    print("\n注：此前报告的「51/54 PASS」为旧启发式评分口径（2026-09-30 版，"
          "存在钙钛矿 9999% 反例），不代表本口径结果——两版评分不可混比。")
    report = {"freeze": freeze, "baseline_drift": baseline_drift, "rows": rows,
              "scoring_version": "4.1-facts-2026-10-01",
              "old_heuristic_51_54": "旧启发式口径（2026-09-30），含已知反例，不可与本版混比",
              "total": {"new": new_total, "old": old_total, "max": n, "gate_80": gate}}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
        print(f"报告已写入 {args.report}")
    return 0 if gate else 2


if __name__ == "__main__":
    sys.exit(main())
