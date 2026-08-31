"""Trigger-rule conditions + deterministic rule selection (roadmap E15-05).

A rule version's ``conditions`` is a :mod:`bbz_rule_dsl` expression over the
**allowlisted, typed** ``TRIGGER_CONTEXT`` (E05-02, ADR-0010) — never code.

* :func:`validate_conditions` is the *publish gate* (E15-10): an unknown field
  or a type-incompatible operator fails here, not at runtime;
* :func:`rule_matches` / :func:`select_matching_rules` evaluate a published
  rule against a normalized inbound signal (E15-04). Selection is deterministic:
  matching rules ordered by ``(priority, rule_id)`` — the engine (E15-09) then
  runs each in turn.

Empty conditions (``{}`` / ``None``) mean "always matches".
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from bbz_rule_dsl import TRIGGER_CONTEXT, Context, RuleDslError, evaluate, parse

#: ordinal for the signal's ``severity`` enum so ``gte`` etc. work numerically
_SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class RuleConditionError(ValueError):
    """A rule condition is not valid for the trigger context (publish error)."""


def validate_conditions(conditions: Mapping[str, Any] | None) -> None:
    """Raise :class:`RuleConditionError` if ``conditions`` cannot be published.

    Delegates the field/type allowlist check to
    :meth:`bbz_rule_dsl.context.ContextSchema.validate` for ``TRIGGER_CONTEXT``.
    """
    if not conditions:
        return
    try:
        TRIGGER_CONTEXT.validate(dict(conditions))
    except RuleDslError as exc:
        raise RuleConditionError(str(exc)) from exc


def signal_to_context(signal: Mapping[str, Any]) -> Context:
    """Flatten a normalized inbound signal (E15-04) into the DSL context.

    Field names follow ``TRIGGER_CONTEXT`` (``calling_number`` / ``called_number``
    rather than the wire ``ani`` / ``dnis``); ``severity`` becomes its numeric
    rank. Fields the signal does not carry resolve to ``None``.
    """
    src: Mapping[str, Any] = signal.get("source") or {}
    severity = src.get("severity")
    return Context(
        {
            "provider": signal.get("provider"),
            "signal_type": signal.get("signal_type"),
            "calling_number": src.get("ani"),
            "called_number": src.get("dnis"),
            "cti_route_point": src.get("cti_route_point"),
            "technical_endpoint_id": src.get("technical_endpoint_id"),
            "external_source_id": src.get("external_source_id"),
            "site": src.get("site"),
            "call_direction": src.get("direction"),
            "call_state": src.get("call_state"),
            "alarm_subtype": src.get("alarm_subtype"),
            "severity": _SEVERITY_RANK.get(severity) if isinstance(severity, str) else None,
        }
    )


def rule_matches(conditions: Mapping[str, Any] | None, signal: Mapping[str, Any]) -> bool:
    """Does a published rule's ``conditions`` match ``signal``? Total + deterministic."""
    if not conditions:
        return True
    return bool(evaluate(parse(dict(conditions)), signal_to_context(signal)))


@dataclass(frozen=True)
class CandidateRule:
    rule_id: uuid.UUID
    priority: int
    conditions: Mapping[str, Any] | None


def select_matching_rules(
    rules: Iterable[CandidateRule], signal: Mapping[str, Any]
) -> list[CandidateRule]:
    """The rules that match ``signal``, ordered by ``(priority, rule_id)`` —
    deterministic even when several rules match (E15-05 AC)."""
    matched = [r for r in rules if rule_matches(r.conditions, signal)]
    return sorted(matched, key=lambda r: (r.priority, str(r.rule_id)))
