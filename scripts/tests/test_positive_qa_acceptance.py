import ast
import json
import re
from pathlib import Path


def _fn():
    path = Path(__file__).resolve().parents[2] / "docs/qa-acceptance/drill_2_5_matrix.py"
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "positive_answer_ok")
    ns = {"re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns["positive_answer_ok"]


def test_known_positive_requires_correct_units_citation_done_no_refusal():
    check = _fn()
    out = {"answer": "内部评估为350Wh/kg [1]。", "done": {"session_id": "s"},
           "citations": [{"id": 1, "title": "seed 内部评估", "primary_section": "atsc"}]}
    assert check(out, "seed")
    for answer in ("无法确认。 [1]", "报告为420Wh/kg [1]", "数值350，无单位 [1]", "350Wh/kg无引用", "350Wh/kg与420Wh/kg [1]"):
        assert not check(dict(out, answer=answer), "seed")
    assert check(dict(out, answer="0.35kWh/kg [1]"), "seed")
    assert not check(dict(out, error="network error"), "seed")
    assert not check(dict(out, done={}), "seed")
