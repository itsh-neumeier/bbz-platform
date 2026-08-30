from __future__ import annotations

import pytest

from bbz_rule_dsl import Context, RuleDslError, evaluate, parse
from bbz_rule_dsl.model import Expr


def test_parse_valid_expression() -> None:
    tree = {
        "op": "and",
        "args": [
            {"op": "eq", "args": [{"field": "provider"}, "coda_video"]},
            {"op": "eq", "args": [{"field": "alarm_subtype"}, "panic_button"]},
        ],
    }
    expr = parse(tree)
    assert isinstance(expr, Expr)
    assert expr.op == "and"
    assert len(expr.args) == 2


def test_unknown_operator_rejected() -> None:
    with pytest.raises(RuleDslError):
        parse({"op": "system", "args": []})


def test_parse_checks_structure_not_field_names() -> None:
    # parse() no longer knows the field set (that is ContextSchema.validate);
    # it only rejects a malformed field reference.
    parse({"op": "eq", "args": [{"field": "anything_goes_here"}, 1]})
    with pytest.raises(RuleDslError):
        parse({"op": "eq", "args": [{"field": ""}, 1]})


def test_context_accepts_any_resolved_values() -> None:
    ctx = Context(values={"provider": "x", "custom": "y"})
    assert ctx.get("provider") == "x"
    assert ctx.get("missing") is None


def test_evaluate_runs_on_a_parsed_expression() -> None:
    expr = parse({"op": "exists", "args": [{"field": "provider"}]})
    assert evaluate(expr, Context(values={"provider": "coda_video"})) is True
    assert evaluate(expr, Context(values={})) is False
