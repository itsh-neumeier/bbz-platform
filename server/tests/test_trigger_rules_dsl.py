"""Trigger-rule conditions + deterministic selection (E15-05) — pure, no DB."""

from __future__ import annotations

import uuid

import pytest

from bbz_core.domain.triggers import (
    CandidateRule,
    RuleConditionError,
    rule_matches,
    select_matching_rules,
    signal_to_context,
    validate_conditions,
)


def _signal(**source: object) -> dict[str, object]:
    return {
        "signal_type": source.pop("signal_type", "BMA_ALARM_CALL"),
        "provider": source.pop("provider", "telephony_cucm"),
        "occurred_at": "2026-08-31T09:00:00Z",
        "received_at": "2026-08-31T09:00:00Z",
        "gateway_node": "BBZ-SRV01",
        "source": source,
    }


# --- validate_conditions (publish gate) --------------------------------


def test_empty_conditions_are_valid_and_always_match() -> None:
    validate_conditions(None)
    validate_conditions({})
    assert rule_matches({}, _signal()) is True
    assert rule_matches(None, _signal()) is True


def test_an_unknown_field_is_a_publish_error() -> None:
    with pytest.raises(RuleConditionError):
        validate_conditions({"op": "eq", "args": [{"field": "not_a_field"}, "x"]})


def test_a_type_incompatible_operator_is_a_publish_error() -> None:
    # severity is numeric in the trigger context; comparing it to a string fails
    with pytest.raises(RuleConditionError):
        validate_conditions({"op": "gte", "args": [{"field": "severity"}, "high"]})
    # ordering a string field
    with pytest.raises(RuleConditionError):
        validate_conditions({"op": "gt", "args": [{"field": "provider"}, "a"]})


def test_a_valid_condition_passes_the_publish_gate() -> None:
    validate_conditions(
        {
            "op": "and",
            "args": [
                {"op": "eq", "args": [{"field": "signal_type"}, "BMA_ALARM_CALL"]},
                {"op": "gte", "args": [{"field": "severity"}, 3]},
            ],
        }
    )


# --- signal_to_context -------------------------------------------------


def test_signal_maps_wire_fields_to_context_names() -> None:
    ctx = signal_to_context(_signal(ani="+49911500", dnis="110", severity="critical"))
    assert ctx.get("calling_number") == "+49911500"
    assert ctx.get("called_number") == "110"
    assert ctx.get("severity") == 4  # critical -> rank 4
    assert ctx.get("workplace") is None  # not carried by the signal


# --- rule_matches -----------------------------------------------------


def test_a_simple_equality_matches_and_rejects() -> None:
    cond = {"op": "eq", "args": [{"field": "called_number"}, "110"]}
    assert rule_matches(cond, _signal(dnis="110")) is True
    assert rule_matches(cond, _signal(dnis="112")) is False


def test_severity_threshold_uses_the_numeric_rank() -> None:
    cond = {"op": "gte", "args": [{"field": "severity"}, 3]}
    assert rule_matches(cond, _signal(severity="critical")) is True
    assert rule_matches(cond, _signal(severity="high")) is True
    assert rule_matches(cond, _signal(severity="medium")) is False


def test_boolean_composition_and_membership() -> None:
    cond = {
        "op": "and",
        "args": [
            {"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]},
            {"op": "in", "args": [{"field": "site"}, ["Nord", "Sued"]]},
            {"op": "not", "args": [{"op": "eq", "args": [{"field": "provider"}, "test"]}]},
        ],
    }
    assert rule_matches(cond, _signal(signal_type="DOORBELL_RINGING", site="Nord")) is True
    assert rule_matches(cond, _signal(signal_type="DOORBELL_RINGING", site="West")) is False


# --- select_matching_rules (determinism) -----------------------------


def test_selection_is_ordered_by_priority_then_rule_id() -> None:
    sig = _signal(dnis="110")
    match = {"op": "eq", "args": [{"field": "called_number"}, "110"]}
    no_match = {"op": "eq", "args": [{"field": "called_number"}, "999"]}

    id_a, id_b, id_c = (uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3))
    rules = [
        CandidateRule(id_c, priority=10, conditions=match),
        CandidateRule(id_a, priority=10, conditions=match),
        CandidateRule(id_b, priority=1, conditions=match),
        CandidateRule(uuid.UUID(int=4), priority=1, conditions=no_match),
    ]

    selected = select_matching_rules(rules, sig)
    assert [r.rule_id for r in selected] == [id_b, id_a, id_c]  # (1,b) < (10,a) < (10,c)

    # deterministic: re-running on a shuffled input gives the same order
    assert select_matching_rules(list(reversed(rules)), sig) == selected
