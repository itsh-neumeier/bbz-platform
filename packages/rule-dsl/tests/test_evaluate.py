"""Rule-DSL evaluator: every operator, edge cases, property/fuzz (E05-01, ADR-0010)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bbz_rule_dsl import Context, Expr, RuleDslError, evaluate, parse

_CTX = Context(
    {
        "provider": "cti",
        "severity": 3,
        "calling_number": "+49301234",
        "call_direction": "inbound",
        "alarm_type": None,
    }
)


def _ev(tree: dict[str, Any], ctx: Context = _CTX) -> bool:
    return evaluate(parse(tree), ctx)


# -- per operator -------------------------------------------------------------


@pytest.mark.parametrize(
    ("tree", "expected"),
    [
        ({"op": "eq", "args": [{"field": "provider"}, "cti"]}, True),
        ({"op": "eq", "args": [{"field": "provider"}, "sip"]}, False),
        ({"op": "ne", "args": [{"field": "severity"}, 1]}, True),
        ({"op": "lt", "args": [{"field": "severity"}, 5]}, True),
        ({"op": "lte", "args": [{"field": "severity"}, 3]}, True),
        ({"op": "gt", "args": [{"field": "severity"}, 3]}, False),
        ({"op": "gte", "args": [{"field": "severity"}, 3]}, True),
        ({"op": "in", "args": [{"field": "call_direction"}, ["inbound", "outbound"]]}, True),
        ({"op": "not_in", "args": [{"field": "provider"}, ["sip", "mock"]]}, True),
        ({"op": "exists", "args": [{"field": "provider"}]}, True),
        ({"op": "exists", "args": [{"field": "alarm_type"}]}, False),
        ({"op": "not", "args": [{"op": "eq", "args": [{"field": "provider"}, "sip"]}]}, True),
        (
            {
                "op": "and",
                "args": [
                    {"op": "eq", "args": [{"field": "provider"}, "cti"]},
                    {"op": "gte", "args": [{"field": "severity"}, 2]},
                ],
            },
            True,
        ),
        (
            {
                "op": "or",
                "args": [
                    {"op": "eq", "args": [{"field": "provider"}, "sip"]},
                    {"op": "eq", "args": [{"field": "call_direction"}, "inbound"]},
                ],
            },
            True,
        ),
    ],
)
def test_operator_results(tree: dict[str, Any], expected: bool) -> None:
    assert _ev(tree) is expected


# -- errors, never "silently true" ------------------------------------------------


def test_unknown_field_is_rejected_at_parse() -> None:
    with pytest.raises(RuleDslError):
        parse({"op": "eq", "args": [{"field": "not_allowed"}, 1]})


def test_unknown_operator_is_rejected_at_parse() -> None:
    with pytest.raises(RuleDslError):
        parse({"op": "regex", "args": []})


def test_type_mismatch_raises_not_true() -> None:
    with pytest.raises(RuleDslError, match="type mismatch"):
        _ev({"op": "lt", "args": [{"field": "provider"}, 5]})


def test_membership_on_non_collection_raises() -> None:
    with pytest.raises(RuleDslError, match="collection"):
        _ev({"op": "in", "args": [{"field": "severity"}, {"field": "severity"}]})


@pytest.mark.parametrize(
    "tree",
    [
        {"op": "eq", "args": [1]},
        {"op": "not", "args": [True, False]},
        {"op": "and", "args": []},
        {"op": "exists", "args": [5]},
    ],
)
def test_bad_arity_or_shape_raises(tree: dict[str, Any]) -> None:
    with pytest.raises(RuleDslError):
        _ev(tree)


def test_evaluate_rejects_a_non_expr() -> None:
    with pytest.raises(RuleDslError):
        evaluate({"op": "eq", "args": []}, _CTX)  # type: ignore[arg-type]


def test_evaluate_rejects_an_operator_that_bypassed_parse() -> None:
    with pytest.raises(RuleDslError, match="operator not allowed"):
        evaluate(Expr(op="regex", args=()), _CTX)


def test_context_get_rejects_unknown_field_at_runtime() -> None:
    with pytest.raises(RuleDslError):
        Context({}).get("definitely_not_allowed")


@pytest.mark.parametrize(
    "tree",
    [
        {},
        {"op": "eq", "args": "not-a-list"},
        {"op": "eq", "args": [{"weird": 1}, 2]},
    ],
)
def test_malformed_trees_raise(tree: Any) -> None:
    with pytest.raises(RuleDslError):
        evaluate(parse(tree), _CTX)


def test_nested_expr_as_operand_and_bare_operands_in_boolean_ops() -> None:
    # a predicate used as a value for eq (exercises Expr-operand resolution)
    assert _ev(
        {
            "op": "eq",
            "args": [{"op": "exists", "args": [{"field": "provider"}]}, True],
        }
    )
    # bare field ref + bare literal as boolean operands of and/or
    assert _ev({"op": "and", "args": [{"field": "provider"}, True]})
    assert _ev({"op": "or", "args": [{"field": "alarm_type"}, True]})
    assert _ev({"op": "not", "args": [{"field": "alarm_type"}]})


def test_deep_nesting_is_bounded() -> None:
    tree: dict[str, Any] = {"op": "eq", "args": [{"field": "severity"}, 3]}
    for _ in range(200):
        tree = {"op": "not", "args": [tree]}
    with pytest.raises(RuleDslError, match="depth"):
        _ev(tree)


# -- property / fuzz --------------------------------------------------------------

_FIELDS = ["provider", "severity", "call_direction", "alarm_type"]
_LEAF = st.one_of(
    st.builds(lambda f: {"field": f}, st.sampled_from(_FIELDS)),
    st.integers(-5, 5),
    st.text(max_size=4),
    st.booleans(),
    st.none(),
)


@st.composite
def _exprs(draw: st.DrawFn, depth: int = 0) -> dict[str, Any]:
    if depth >= 3 or draw(st.booleans()):
        op = draw(st.sampled_from(["eq", "ne", "lt", "gt", "in", "not_in"]))
        return {"op": op, "args": [draw(_LEAF), draw(_LEAF)]}
    op = draw(st.sampled_from(["and", "or", "not"]))
    n = 1 if op == "not" else draw(st.integers(1, 3))
    return {"op": op, "args": [draw(_exprs(depth + 1)) for _ in range(n)]}


@settings(max_examples=300, deadline=None)
@given(_exprs())
def test_fuzz_random_ast_never_crashes_and_is_deterministic(tree: dict[str, Any]) -> None:
    try:
        parsed = parse(tree)
    except RuleDslError:
        return  # parse rejection is fine
    try:
        first = evaluate(parsed, _CTX)
    except RuleDslError:
        return  # a typed failure is fine — must never be a raw crash
    assert isinstance(first, bool)
    assert evaluate(parsed, _CTX) is first  # deterministic
