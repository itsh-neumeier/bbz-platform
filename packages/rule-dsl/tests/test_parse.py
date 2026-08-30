from __future__ import annotations

import pytest

from bbz_rule_dsl import Context, RuleDslError, UnknownField, evaluate, parse
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


def test_non_allowlisted_field_rejected() -> None:
    with pytest.raises(UnknownField):
        parse({"op": "eq", "args": [{"field": "os.system"}, 1]})


def test_context_rejects_unknown_keys() -> None:
    with pytest.raises(UnknownField):
        Context(values={"provider": "x", "danger": "y"})


def test_evaluate_runs_on_a_parsed_expression() -> None:
    expr = parse({"op": "exists", "args": [{"field": "provider"}]})
    assert evaluate(expr, Context(values={"provider": "coda_video"})) is True
    assert evaluate(expr, Context(values={})) is False
