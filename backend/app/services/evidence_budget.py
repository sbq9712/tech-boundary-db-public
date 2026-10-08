"""Fair, deterministic evidence budgets across sources and documents."""
from __future__ import annotations


def fair_budgets(lengths: list[int], total: int) -> list[int]:
    """Water-fill: short items release unused space to the remaining items."""
    result = [0] * len(lengths)
    pending = list(range(len(lengths)))
    remaining = max(0, total)
    while pending:
        share, extra = divmod(remaining, len(pending))
        short = [i for i in pending if lengths[i] <= share]
        if not short:
            for rank, i in enumerate(pending):
                result[i] = share + (rank < extra)
            break
        for i in short:
            result[i] = lengths[i]
            remaining -= lengths[i]
            pending.remove(i)
    return result


def budget_citations(citations: list[dict], budget: int, labels: dict,
                     order: tuple, render_block) -> tuple[list[dict], bool]:
    groups = [(s, [c for c in citations if c.get("primary_section") == s])
              for s in order]
    groups = [(s, items) for s, items in groups if items]
    separators = len("\n\n---\n\n") * max(0, len(groups) - 1)
    lengths = [len(f"【{labels[s]}】\n") + len("\n\n") * (len(items) - 1)
               + sum(len(render_block(c)[0]) for c in items)
               for s, items in groups]
    quotas = fair_budgets(lengths, max(0, budget - separators))
    selected = []
    truncated = False
    for (section, items), quota in zip(groups, quotas):
        available = max(0, quota - len(f"【{labels[section]}】\n")
                        - 2 * (len(items) - 1))
        caps = fair_budgets([len(render_block(c)[0]) for c in items], available)
        for citation, cap in zip(items, caps):
            current = dict(citation)
            body = str(current.get("chunk_text") or current.get("body_snippet") or "")
            if len(render_block(current)[0]) > cap:
                truncated = True
                # Rendering adds only a fixed metadata prefix/suffix around body.
                allowed = cap - (len(render_block(current)[0]) - len(body))
                if allowed <= 0 or not body:
                    continue
                text = body[:allowed]
                current["body_snippet"] = text
                if current.get("document_id"):
                    current["chunk_text"] = text
                current["context_truncated"] = True
            selected.append(current)
    return selected, truncated or any(c.get("context_truncated") for c in selected)
