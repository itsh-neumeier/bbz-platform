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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from bbz_core.domain.events.state import EventPriority
from bbz_core.domain.triggers.actions import SUPPORTED_ACTION_TYPES, TriggerActionType
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


def validate_actions(actions: Sequence[Any]) -> list[str]:
    """Structural check of a rule version's ``actions`` list (publish gate, E15-10).

    Returns a list of human-readable problems (empty = OK). Each action must be
    an object with a ``type`` the engine can run today, and carry the config
    that type needs. A DTMF *code* in a ``send_dtmf_profile`` action is rejected
    outright — the code is a secret held by the integration, never the rule
    (ADR-0004, MASTER_PROMPT §30).
    """
    problems: list[str] = []
    for index, raw in enumerate(actions):
        if not isinstance(raw, Mapping):
            problems.append(f"action {index}: must be an object")
            continue
        raw_type = str(raw.get("type", ""))
        try:
            action_type = TriggerActionType(raw_type)
        except ValueError:
            problems.append(f"action {index}: unknown type {raw_type!r}")
            continue
        if action_type not in SUPPORTED_ACTION_TYPES:
            problems.append(f"action {index}: {raw_type} is not available yet")
            continue
        problems.extend(
            f"action {index}: {msg}" for msg in _action_config_problems(action_type, raw)
        )
    return problems


def _action_config_problems(action_type: TriggerActionType, action: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    if (
        action_type is TriggerActionType.ATTACH_WORKFLOW
        and not str(action.get("template_key", "")).strip()
    ):
        out.append("attach_workflow requires template_key")
    if action_type is TriggerActionType.SHOW_CLIENT_POPUP and not _is_uuid(
        action.get("workplace_id")
    ):
        out.append("show_client_popup requires a workplace_id (uuid)")
    if action_type is TriggerActionType.CREATE_EVENT and "priority" in action:
        try:
            EventPriority(str(action["priority"]))
        except ValueError:
            out.append(f"invalid priority {action['priority']!r}")
    if action_type is TriggerActionType.SEND_DTMF_PROFILE:
        if not str(action.get("dtmf_profile_id", "")).strip():
            out.append("send_dtmf_profile requires dtmf_profile_id")
        if "code" in action or "dtmf" in action:
            out.append("a DTMF code must never appear in a rule action")
    return out


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError):
        return False
    return True


def publish_blockers(conditions: Mapping[str, Any] | None, actions: Sequence[Any]) -> list[str]:
    """Everything that would stop this conditions+actions pair being published."""
    blockers: list[str] = []
    try:
        validate_conditions(conditions)
    except RuleConditionError as exc:
        blockers.append(f"conditions: {exc}")
    if not actions:
        blockers.append("a rule version must have at least one action")
    blockers.extend(validate_actions(actions))
    return blockers


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
