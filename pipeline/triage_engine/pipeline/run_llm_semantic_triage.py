# -*- coding: utf-8 -*-
"""三库大模型语义判定管线（2026-09-18 修复轮，约束见《分类基准与AI执行约束_20260918.md》）。

流程：base.read_rows() 取数并按 build() 同款去重 → 圈定判定范围（默认：规则层域外/T25
待定 + 本轮 10 条问题 URL；--all 全量）→ 按批调用 LLM（Anthropic Messages 协议，
配置读仓库根 .env：LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）→ 断点续跑（audit JSONL）
→ 汇总为 llm_semantic_decisions.json（url→决策），由 build_strict_semantic_triage.build()
合并覆盖规则层结果。

合并策略（写在输出文件 meta 中）：confidence=high 或规则层未决（域外/T25/AI00 停根）时采纳 LLM 裁决；
medium/low 只用于营救未决条目，不覆盖规则层已明确判定。--force-all 可关闭该过滤。

运行：PYTHONIOENCODING=utf-8 ../../.venv/Scripts/python.exe run_llm_semantic_triage.py [--all] [--limit N] [--batch 8] [--dry-run] [--force-all]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import build_github_triage as base  # noqa: E402
from cls_data import TYPES  # noqa: E402
from build_strict_semantic_triage import (  # noqa: E402
    EXTENSION_DOMAINS, classify_domain_semantic, classify_type_semantic)

try:  # docx v2（2026-09-21）依次分类路由摘要；旧版 docx 无此常量时为空串降级
    from lit_rules_data import ROUTING_DIGEST
except ImportError:
    ROUTING_DIGEST = ""

# 本轮用户反馈的 10 条问题（URL 片段 / 标题关键词），无论规则层是否已修复都送 LLM 复核。
PROBLEM_KEYS = [
    "S0306261926008524", "S0306261926008020", "S030626192600855X", "S030626192600797X",
    "S0301421526003691", "zJQkeClNGJrgfoOs4NkuAg", "fQE2mt9p9k_fG0c7pUONvQ",
    "bFtpO3gkProT8r15TPtG1g", "bb3vV9qEuK3KeXL6kucIZg", "zTLCn5UammHH7A_MgweZVA",
    "3qtvmTfv2tz4lCZvSbaT7Q", "a6ZcquzesGB87REqOH-FjA",
]
PROBLEM_TITLE_KEYS = ["Statkraft"]

AUDIT_PATH = os.path.join(HERE, "llm_semantic_audit.jsonl")
DECISIONS_PATH = os.path.join(HERE, "llm_semantic_decisions.json")

SYSTEM_PROMPT = """你是能源/零碳/AI 行业情报库的语义分类裁决器。任务：通读每条记录的标题与正文（含摘要、digest），\
把主技术对象判入行业图景技术分类，把主事件判入新闻类型分类。

【强约束（违反任一即为错误）】
1 语义理解为准：以两份基准 docx 的语义定义为准绳，不是关键词门槛；不得以“动作、指标、瓶颈不足”为域外理由——主对象明确即入域。
2 默认域内：只有与零碳产业/AI与智能科技/通用技术树完全无关（纯娱乐、体育、一般财经宏观、期刊运营征稿）才可判“域外”，且必须在 reason 给出明确域外理由。
3 标题语义可单独支撑：正文为空或只有 digest 时按标题判域；文献（src=literature 或标题为论文题名）类型一律 T01；删链微信文章用 digest 判定，不得落 T25。【2026-09-24 v3.1 载体前提】src=literature 一律 T01；wechat/news 中出现 DOI（字段/链接/正文）只是引用线索——有 DOI ≠ 论文：仅当主对象是论文本体（全文转载、学术速递、以论文题名为题、正文即摘要/研究内容）才判 T01；报道/解读/分析/评论某论文（附 DOI）按主事件分型（多为 T23 深度分析），不得因有 DOI 判 T01。
4 载体形态优先：直播预约/预告/报名→T24；『N部门/部委发文+行动部署』→T19（吨位金额只是政策量化目标，不判 T15/T16）；标题阶段跃迁（开工/扩建/建成/并网/投运/发布/破纪录）→T08/T09/T10/T07，不落 T23。
5 主事件锚定：类型以标题+导语主事件为准；尾部栏目/往期回顾/推广/日报后段其他事件只作 alternatives。
6 领域取最深层适用完整路径；方法工具背景不得覆盖主对象。【2026-09-24 预置叶冻结】domain_path 必须逐字取自【技术领域菜单】或【语义树叶路径】的预置节点（含“运行扩展域”）；基准无完全匹配叶时，选语义最近的一个预置叶并在 reason 说明近似理由，禁止自拟“扩展:”新路径、禁止新增节点（暂时冻结）。只有与零碳产业/AI与智能科技/通用技术完全无关才可判“域外”。
7 输出契约（严格 JSON 数组，每元素）：{"i":记录编号,"domain_path":"预置完整路径或‘域外’","domain_no":"D/E/GT 编号或空","type_id":"T01–T25","terms":["标题/正文中的领域关键词≤4个"],"alternatives":["第二独立事件的type_id"],"reason":"一句中文：主事件+判定依据","confidence":"high|medium|low"}
8 type_id 必须逐字是 T01–T25 之一，禁止新增类型；不确定且无载体身份才用 T25；domain_no 不确定就留空，由路径兜底。

【依次分类路由（v2 2026-09-21：必须按此执行——先定主对象，再 Q1零碳→Q2AI→Q3通用技术 逐层路由，下钻最深叶，禁止停留在分支根）】
__ROUTING__

【技术领域菜单】（domain_no 优先用编号；路径须与菜单逐字一致——预置叶冻结，禁止自拟新路径）
__DOMAIN_MENU__

【语义树叶路径】（domain_no 留空、domain_path 填下列完整路径之一时，评分按语义域处理）
__LEAF_MENU__

【新闻类型菜单】
__TYPE_MENU__"""


def load_env():
    root = HERE
    for _ in range(4):
        if os.path.exists(os.path.join(root, ".env")):
            break
        root = os.path.dirname(root)
    env = {}
    p = os.path.join(root, ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def build_menus():
    dom_lines = [f"{d['no']} {d['name']}" for d in base.DOMS]
    dom_lines += [f"{d['no']} {d['name']}（运行扩展域）" for d in EXTENSION_DOMAINS]
    leaf_lines = []
    for leaf in base.LIT_LEAVES:
        if leaf.get("target") in (None, "E99"):
            leaf_lines.append(leaf["path"])
    type_lines = [f"{t['id']} {t['name']}：{str(t.get('definition', ''))[:56]}" for t in TYPES]
    return ("\n".join(dom_lines), "\n".join(dict.fromkeys(leaf_lines)), "\n".join(type_lines))


def norm_path(s):
    return re.sub(r"\s*", "", str(s or "")).replace("｜", "|").replace("＞", ">")


def resolve_domain_no(dec):
    """把 LLM 的 domain_path/domain_no 归一到注册编号；无法归一时保留路径由合并层兜底。"""
    no = str(dec.get("domain_no") or "").strip().upper()
    if no and any(d["no"] == no for d in list(base.DOMS) + EXTENSION_DOMAINS):
        return no
    path = norm_path(dec.get("domain_path"))
    for d in list(base.DOMS) + EXTENSION_DOMAINS:
        if norm_path(d["name"]) and norm_path(d["name"]) in path:
            return d["no"]
    for leaf in base.LIT_LEAVES:
        if norm_path(leaf["path"]) == path:
            return ""  # 语义叶：编号留空，路径兜底
    return no


def dedup_rows():
    rows = base.read_rows()
    seen, dedup = {}, []
    for item in rows:
        key = re.sub(r"[\W_]+", "", (item["title"] or "").lower(), flags=re.U) or item.get("url", "")
        if key in seen:
            continue
        seen[key] = item
        dedup.append(item)
    return rows, dedup


def select_scope(dedup, want_all, limit):
    scope = []
    for idx, item in enumerate(dedup):
        url = item.get("url") or item.get("doi") or ""
        title = item.get("title") or ""
        is_problem = any(k in url for k in PROBLEM_KEYS) or any(k in title for k in PROBLEM_TITLE_KEYS)
        dom = classify_domain_semantic(item)
        typ = classify_type_semantic(item)
        # 2026-09-21 v2 落地修复：AI00 停根（semantic_branch_ai，规则层自认"证据不足以细分"）
        # 属未决——docx v2 判定停根违规，medium/low 叶裁决也应营救，不得按"已决"要求 high。
        undecided = (dom["disp"] == "域外" or typ["tid"] == "T25"
                     or (isinstance(dom.get("primary"), dict)
                         and dom["primary"].get("id") == "semantic_branch_ai"))
        if want_all or is_problem or undecided:
            scope.append({"i": idx, "url": url, "item": item, "rule_dom": dom["label"],
                          "rule_disp": dom["disp"], "rule_typ": typ["tid"],
                          "undecided": undecided, "problem": is_problem})
    if limit:
        scope = scope[:limit]
    return scope


def call_llm(env, system, user, timeout):
    url = env.get("LLM_BASE_URL", "").rstrip("/") + "/v1/messages"
    payload = json.dumps({
        "model": env.get("LLM_MODEL", "glm-5.2"),
        "max_tokens": int(env.get("LLM_MAX_TOKENS") or 4096),
        "temperature": float(env.get("LLM_TEMPERATURE") or 0),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "content-type": "application/json",
        "x-api-key": env.get("LLM_API_KEY", ""),
        "authorization": "Bearer " + env.get("LLM_API_KEY", ""),
        "anthropic-version": "2023-06-01",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    parts = data.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def extract_json_array(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) else None
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全量判定（默认仅域外/T25+问题URL）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--force-all", action="store_true", help="decisions 不过滤 confidence/未决条件")
    ap.add_argument("--sleep", type=float, default=8.0, help="批间节流秒数（防 429）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env()
    if not env.get("LLM_API_KEY") or not env.get("LLM_BASE_URL"):
        print("[fatal] .env 缺 LLM_API_KEY/LLM_BASE_URL")
        sys.exit(2)
    timeout = int(env.get("LLM_TIMEOUT_SECONDS") or 120)

    rows, dedup = dedup_rows()
    scope = select_scope(dedup, args.all, args.limit)
    n_undecided = sum(1 for s in scope if s["undecided"])
    n_problem = sum(1 for s in scope if s["problem"])
    print(f"rows={len(rows)} dedup={len(dedup)} scope={len(scope)} "
          f"(未决={n_undecided} 问题复核={n_problem}) batch={args.batch}")
    if args.dry_run:
        for s in scope[:20]:
            print(f"  i={s['i']} [{s['rule_disp']}/{s['rule_typ']}] {s['item']['title'][:40]}")
        return

    dom_menu, leaf_menu, type_menu = build_menus()
    system = (SYSTEM_PROMPT.replace("__ROUTING__", ROUTING_DIGEST)
              .replace("__DOMAIN_MENU__", dom_menu)
              .replace("__LEAF_MENU__", leaf_menu).replace("__TYPE_MENU__", type_menu))

    done = {}
    if os.path.exists(AUDIT_PATH):
        with open(AUDIT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                for dec in rec.get("decisions", []):
                    if isinstance(dec, dict) and "i" in dec:
                        done[int(dec["i"])] = dec
        print(f"resume: {len(done)} 已判定")

    audit_f = open(AUDIT_PATH, "a", encoding="utf-8")
    sent = 0
    for start in range(0, len(scope), args.batch):
        chunk = [s for s in scope[start:start + args.batch] if s["i"] not in done]
        if not chunk:
            continue
        items_js = json.dumps([{
            "i": s["i"], "src": s["item"].get("src", ""),
            "title": (s["item"].get("title") or "")[:160],
            "body": (s["item"].get("body") or "")[:1100],
        } for s in chunk], ensure_ascii=False)
        user = ("判定以下记录（body 为空时按约束 3 用标题判定；src=literature 一律 T01）：\n" + items_js
                + "\n\n只输出 JSON 数组，元素数与输入记录数一致，i 一一对应。")
        reply = None
        for attempt in range(5):
            try:
                reply = call_llm(env, system, user, timeout)
                break
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
                # 429 限流：长退避（30/60/120/240s）；其他错误短退避。
                is_429 = getattr(e, "code", None) == 429
                wait = (30 * (2 ** attempt)) if is_429 else 5 * (attempt + 1)
                print(f"  [retry {attempt + 1}] i={[s['i'] for s in chunk]} {e} → 等 {wait}s")
                time.sleep(wait)
        if reply is None:
            print(f"  [skip] 批次失败 i={[s['i'] for s in chunk]}")
            continue
        decs = extract_json_array(reply) or []
        for dec in decs:
            if isinstance(dec, dict) and "i" in dec:
                try:
                    dec["i"] = int(dec["i"])
                except (TypeError, ValueError):
                    continue
                dec["domain_no"] = resolve_domain_no(dec)
                done[dec["i"]] = dec
        audit_f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                  "is": [s["i"] for s in chunk], "decisions": decs},
                                 ensure_ascii=False) + "\n")
        audit_f.flush()
        sent += 1
        print(f"  batch {sent}: i={[s['i'] for s in chunk]} → {len(decs)} 条")
        time.sleep(args.sleep)  # 批间节流，避免突发限流（429）
    audit_f.close()

    # 汇总 decisions：合并策略见文件头。
    by_i = {s["i"]: s for s in scope}
    decisions, skipped = {}, 0
    for i, dec in done.items():
        s = by_i.get(i)
        if not s:
            continue
        conf = str(dec.get("confidence", "")).lower()
        accept = args.force_all or conf == "high" or s["undecided"]
        if not accept:
            skipped += 1
            continue
        decisions[s["url"]] = {
            "domain_path": str(dec.get("domain_path") or ""),
            "domain_no": str(dec.get("domain_no") or ""),
            "type_id": str(dec.get("type_id") or ""),
            "terms": [str(t) for t in (dec.get("terms") or [])][:4],
            "alternatives": [str(a) for a in (dec.get("alternatives") or [])][:3],
            "reason": str(dec.get("reason") or "")[:160],
            "confidence": conf or "medium",
            "ruleLayerRef": f"{s['rule_disp']}/{s['rule_typ']}",
            "isProblemCase": s["problem"],
        }
    with open(DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": "2026-09-24-v3.1（预置叶冻结＋载体前提：DOI×语义共决，有 DOI ≠ 论文）", "model": env.get("LLM_MODEL"),
                   "policy": "confidence=high 或规则层未决（域外/T25/AI00 停根）时采纳；--force-all 可全量采纳",
                   "judged": len(done), "accepted": len(decisions), "skipped_low_conf": skipped,
                   "decisions": decisions}, f, ensure_ascii=False, indent=1)
    print(f"done: judged={len(done)} accepted={len(decisions)} skipped_low_conf={skipped} → {DECISIONS_PATH}")


if __name__ == "__main__":
    main()
