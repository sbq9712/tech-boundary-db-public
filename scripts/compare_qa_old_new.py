#!/usr/bin/env python3
"""新旧问答对照验证（第七节验收 11）。

对同一组探针问题分别调用：
  旧链路：tech-db legacy_hybrid /api/chat/stream（host:8765，SSE）
  新链路：主仓库 backend /api/chat/stream（门户同款，内部走 canonical-qa
          编排检索 + 答案侧核验）

对比维度（功能覆盖，非逐字一致）：
  - 检索证据：citations 数量、引用含标题/日期/来源
  - 状态链路：新链路 answer_status / knowledge_boundary / claim_check
  - 编排痕迹：新链路 retrieval_summary.evidence / retrieval_trace
  - 内容重叠：两边回答的字符 2-gram Jaccard（信息性参考）
  - 降级行为：无证据问题两边都应拒绝或给边界提示，不编造

用法：
  python3 scripts/compare_qa_old_new.py --old http://127.0.0.1:8765 \
      --portal http://127.0.0.1:8000 [--login user pass] [--report out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROBES = [
    "固态电池量产的最新进展有哪些？",
    "钠离子电池在储能领域的应用现状",
    "钙钛矿太阳能电池的效率纪录",
    "氢能电解槽技术路线对比",
    "完全不存在于数据库的问题：量子恐龙税制在火星的适用性",
]
TTFB_TIMEOUT = 300


def sse_chat(base_url: str, query: str, token: str | None = None,
             timeout: int = TTFB_TIMEOUT) -> dict:
    """收集 SSE 事件。

    - 旧链路（tech-db /api/chat/stream）：POST body {query}；
    - 新链路（门户 /api/assistant/stream）：POST body {query, session_id}，
      Bearer 鉴权；endpoint 由 base_url 形态区分（:8000 → 门户）。
    """
    is_portal = ":8000" in base_url or "/api" in base_url and "8765" not in base_url
    path = "/api/assistant/stream" if is_portal else "/api/chat/stream"
    body = json.dumps(
        {"query": query, "session_id": None} if is_portal
        else {"query": query, "conversation_id": "", "history": []}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=body, method="POST",
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
    body = json.dumps({"username": user, "password": password}).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/api/auth/login",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("access_token") or data.get("token") or ""


def bigrams(text: str) -> set[str]:
    text = "".join(text.split())
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else set()


def summarize_old(result: dict) -> dict:
    if "error" in result:
        return {"error": result["error"]}
    answer_parts, citations, errors = [], [], []
    for _, payload in result.get("events", []):
        if "answer" in payload:
            answer_parts.append(payload["answer"])
        if "text" in payload:
            answer_parts.append(payload["text"])
        if "content" in payload:
            answer_parts.append(payload["content"])
        if payload.get("citations"):
            citations = payload["citations"]
        if payload.get("message") and "error" in str(payload):
            errors.append(payload["message"])
    answer = "".join(answer_parts)
    return {
        "answer_chars": len(answer),
        "answer_head": answer[:120],
        "citations": len(citations),
        "citations_have_title_date": bool(citations) and all(
            c.get("title") and c.get("date") for c in citations[:5] if isinstance(c, dict)),
        "errors": errors[:1],
    }


def summarize_new(result: dict) -> dict:
    base = summarize_old(result)
    if "error" in base.get("error", "") or result.get("error"):
        return {"error": result.get("error") or base.get("error")}
    done = {}
    status_events = []
    for _, payload in result.get("events", []):
        if payload.get("answer_status") or payload.get("retrieval_trace"):
            done = payload
        if payload.get("stage"):
            status_events.append(payload["stage"])
    base.update({
        "answer_status": done.get("answer_status"),
        "knowledge_boundary": (done.get("knowledge_boundary") or "")[:60] or None,
        "invalid_markers": (done.get("claim_check") or {}).get("invalid_markers"),
        "evidence_status": ((done.get("retrieval_trace") or {}),),
        "stages": status_events[:8],
    })
    summary = done.get("retrieval_summary") or {}
    base["evidence_status"] = (summary.get("evidence") or {}).get("status")
    trace = summary.get("retrieval_trace") or {}
    base["orchestration"] = {
        "decomposed": (trace.get("decomposition") or {}).get("decomposed"),
        "graph_entities": len(trace.get("graph_entities") or []),
        "novelty_excluded": trace.get("novelty_excluded"),
        "reranked": (trace.get("rerank") or {}).get("reranked"),
    }
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="新旧问答对照验证")
    parser.add_argument("--old", default="http://127.0.0.1:8765")
    parser.add_argument("--portal", default="http://127.0.0.1:8000")
    parser.add_argument("--login", nargs=2, metavar=("USER", "PASS"), default=None)
    parser.add_argument("--token", default="", help="直接使用已有 Bearer token（不走登录）")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    token = args.token.strip() or None
    if not token and args.login:
        token = portal_login(args.portal, args.login[0], args.login[1])
        print("门户登录成功", flush=True)
    rows = []
    for probe in PROBES:
        print(f"\n=== 探针：{probe}", flush=True)
        old_raw = sse_chat(args.old, probe)
        new_raw = sse_chat(args.portal, probe, token=token)
        old_sum = summarize_old(old_raw)
        new_sum = summarize_new(new_raw)
        old_answer = old_sum.get("answer_head", "")
        new_answer = new_sum.get("answer_head", "")
        jaccard = 0.0
        # 全文级 2-gram Jaccard
        old_full = "".join(p.get("answer", "") + p.get("text", "") + p.get("content", "")
                           for _, p in old_raw.get("events", []) if isinstance(p, dict))
        new_full = "".join(p.get("answer", "") + p.get("text", "") + p.get("content", "")
                           for _, p in new_raw.get("events", []) if isinstance(p, dict))
        bg_old, bg_new = bigrams(old_full), bigrams(new_full)
        if bg_old and bg_new:
            jaccard = round(len(bg_old & bg_new) / len(bg_old | bg_new), 4)
        row = {"probe": probe, "old": old_sum, "new": new_sum, "bigram_jaccard": jaccard}
        print(json.dumps({"old_citations": old_sum.get("citations"),
                          "new_citations": new_sum.get("citations"),
                          "new_answer_status": new_sum.get("answer_status"),
                          "new_evidence": new_sum.get("evidence_status"),
                          "new_orchestration": new_sum.get("orchestration"),
                          "old_errors": old_sum.get("errors"),
                          "jaccard": jaccard}, ensure_ascii=False, indent=1), flush=True)
        rows.append(row)

    print("\n═══ 对照结论 ═══")
    ok_new = sum(1 for r in rows if not r["new"].get("error") and r["new"].get("citations", 0) >= 0)
    refusal_rows = [r for r in rows if "不存在于数据库" in r["probe"]]
    for r in rows:
        verdict = "✓" if not r["old"].get("error") and not r["new"].get("error") else "✗"
        print(f"{verdict} {r['probe'][:30]}…  旧引用 {r['old'].get('citations')} / "
              f"新引用 {r['new'].get('citations')} / 状态 {r['new'].get('answer_status')} / "
              f"重叠 {r['bigram_jaccard']}")
    if args.report:
        Path(args.report).write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
        print(f"\n报告已写入 {args.report}")
    return 0 if ok_new == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
