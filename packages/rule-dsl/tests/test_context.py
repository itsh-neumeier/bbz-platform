"""Typed context registry: validation at publish time, context separation (E05-02)."""

from __future__ import annotations

from typing import Any

import pytest

from bbz_rule_dsl import (
    TRIGGER_CONTEXT,
    WORKFLOW_CONTEXT,
    ContextSchema,
    FieldType,
    RuleDslError,
    UnknownField,
)

# a throwaway schema exercising the LIST field type
_WITH_LIST = ContextSchema(
    "t", {"tags": FieldType.LIST, "provider": FieldType.STRING, "severity": FieldType.NUMBER}
)


def _ok(schema: Any, tree: dict[str, Any]) -> None:
    schema.validate(tree)


def _bad(schema: Any, tree: dict[str, Any]) -> None:
    with pytest.raises(RuleDslError):
        schema.validate(tree)


def test_valid_trigger_expression_passes() -> None:
    _ok(
        TRIGGER_CONTEXT,
        {
            "op": "and",
            "args": [
                {"op": "eq", "args": [{"field": "provider"}, "cti"]},
                {"op": "gte", "args": [{"field": "severity"}, 2]},
                {"op": "in", "args": [{"field": "call_direction"}, ["inbound", "outbound"]]},
            ],
        },
    )


def test_unknown_field_fails_at_validate() -> None:
    with pytest.raises(UnknownField):
        TRIGGER_CONTEXT.validate({"op": "eq", "args": [{"field": "no_such_field"}, "x"]})


def test_order_op_on_a_string_field_is_a_type_error() -> None:
    _bad(TRIGGER_CONTEXT, {"op": "lt", "args": [{"field": "provider"}, "z"]})


def test_number_field_compared_to_string_literal_is_a_type_error() -> None:
    _bad(TRIGGER_CONTEXT, {"op": "eq", "args": [{"field": "severity"}, "high"]})


def test_membership_needs_a_list_on_the_right() -> None:
    _bad(TRIGGER_CONTEXT, {"op": "in", "args": [{"field": "provider"}, "cti"]})


def test_membership_list_item_type_is_checked() -> None:
    _bad(TRIGGER_CONTEXT, {"op": "in", "args": [{"field": "severity"}, [1, "two", 3]]})


def test_contexts_are_separated() -> None:
    # a trigger field is not visible to the workflow context and vice versa
    with pytest.raises(UnknownField):
        WORKFLOW_CONTEXT.validate({"op": "eq", "args": [{"field": "provider"}, "cti"]})
    with pytest.raises(UnknownField):
        TRIGGER_CONTEXT.validate({"op": "eq", "args": [{"field": "branch_key"}, "b1"]})


def test_valid_workflow_expression_passes() -> None:
    _ok(
        WORKFLOW_CONTEXT,
        {
            "op": "or",
            "args": [
                {"op": "eq", "args": [{"field": "event_priority"}, "critical"]},
                {"op": "eq", "args": [{"field": "operator_confirmed"}, True]},
                {"op": "gt", "args": [{"field": "step_completed_count"}, 0]},
            ],
        },
    )


def test_exists_takes_a_field_reference_only() -> None:
    _ok(TRIGGER_CONTEXT, {"op": "exists", "args": [{"field": "alarm_subtype"}]})
    _bad(TRIGGER_CONTEXT, {"op": "exists", "args": [5]})


def test_binary_op_with_wrong_arity_is_rejected() -> None:
    _bad(TRIGGER_CONTEXT, {"op": "eq", "args": [{"field": "provider"}]})


def test_bare_field_ref_as_boolean_operand_is_checked_for_existence() -> None:
    _ok(WORKFLOW_CONTEXT, {"op": "and", "args": [{"field": "operator_confirmed"}]})
    _bad(WORKFLOW_CONTEXT, {"op": "and", "args": [{"field": "nope"}]})


def test_nested_predicates_as_comparison_operands() -> None:
    p = {"op": "exists", "args": [{"field": "provider"}]}
    _ok(TRIGGER_CONTEXT, {"op": "eq", "args": [p, p]})


def test_validate_accepts_a_prebuilt_expr() -> None:
    from bbz_rule_dsl import parse

    TRIGGER_CONTEXT.validate(parse({"op": "eq", "args": [{"field": "provider"}, "cti"]}))


def test_list_typed_field_on_the_right_of_membership() -> None:
    _WITH_LIST.validate({"op": "in", "args": [{"field": "provider"}, {"field": "tags"}]})
    # a non-list field on the right is rejected
    with pytest.raises(RuleDslError):
        _WITH_LIST.validate({"op": "in", "args": [{"field": "provider"}, {"field": "severity"}]})


def test_list_literal_matches_list_field_type() -> None:
    _WITH_LIST.validate({"op": "eq", "args": [{"field": "tags"}, ["a", "b"]]})
    with pytest.raises(RuleDslError):
        _WITH_LIST.validate({"op": "eq", "args": [{"field": "tags"}, "not-a-list"]})
