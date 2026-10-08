"""Check semantics of the archive features against the current architecture."""

from __future__ import annotations

import itertools
from pathlib import Path

from ethos_aegis.agent.scaffolds import AutonomicSentinel
from ethos_aegis.veriflow import And, BoolConst, F, Not, Or, Symbol, T, simplify


def evaluate(expr, values):
    if isinstance(expr, Symbol):
        return values[expr.name]
    if isinstance(expr, BoolConst):
        return expr.value
    if isinstance(expr, Not):
        return not evaluate(expr.expr, values)
    if isinstance(expr, And):
        return evaluate(expr.left, values) and evaluate(expr.right, values)
    if isinstance(expr, Or):
        return evaluate(expr.left, values) or evaluate(expr.right, values)
    raise TypeError("Unknown expression")


def test_boolean_simplification_preserves_truth_tables():
    p, q = Symbol("P"), Symbol("Q")
    formulas = [
        Not(Not(p)),
        Not(And(p, q)),
        Not(Or(p, q)),
        And(p, T),
        Or(p, F),
        And(p, F),
        Or(p, T),
        And(p, p),
        Or(p, p),
        And(p, Or(p, q)),
        Or(p, And(p, q)),
    ]
    for formula in formulas:
        for a, b in itertools.product([False, True], repeat=2):
            values = {"P": a, "Q": b}
            assert evaluate(formula, values) == evaluate(simplify(formula), values)


def test_change_intake_uses_ast_and_does_not_rewrite_source(tmp_path: Path):
    source = tmp_path / "changed.py"
    source.write_text("# eval(x) in a comment\ndef f(x):\n    return eval(x)\n")
    sentinel = AutonomicSentinel(tmp_path)
    first = sentinel.poll_once()
    assert len(first) == 1 and len(first[0].findings) == 1
    assert first[0].findings[0].confidence.value == "hypothesis"
    assert "return eval(x)" in source.read_text()
    assert sentinel.poll_once() == []
    source.write_text("def f(x):\n    return x\n")
    second = sentinel.poll_once()
    assert second[0].sha256_before == first[0].sha256_after
    assert not second[0].findings
