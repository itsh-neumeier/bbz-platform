"""Typed trigger-action kinds (roadmap E15-03; ``.ai/TECHNICAL_TRIGGERS.md``).

Actions are **typed, not arbitrary scripts** (MASTER_PROMPT §29/§33). A rule's
``actions`` JSON is a list of objects each carrying a ``type`` from
:class:`TriggerActionType`. The engine (E15-09) runs them in order:

* :data:`TRANSACTIONAL_ACTION_TYPES` run inside the same transaction as the
  ``trigger_executions`` ledger row — a domain-state change (``create_event``,
  ``attach_workflow``);
* :data:`OUTBOX_ACTION_TYPES` enqueue exactly one ``external_action_outbox`` row
  (``action_type`` == the enum value) and are delivered once by the dispatcher.

``launch_catalog_app`` is policy-controlled and only reachable when the
workplace/role policy allows it (E10 catalog).
"""

from __future__ import annotations

import enum


class TriggerActionType(enum.StrEnum):
    CREATE_EVENT = "create_event"
    ATTACH_WORKFLOW = "attach_workflow"
    SHOW_CLIENT_POPUP = "show_client_popup"
    NOTIFY = "notify"
    INTEGRATION_ACTION = "integration_action"
    OPEN_CAMERA = "open_camera"
    OPEN_CAMERA_GROUP = "open_camera_group"
    ANSWER_CALL = "answer_call"
    SEND_DTMF_PROFILE = "send_dtmf_profile"
    HANGUP_CALL = "hangup_call"
    LAUNCH_CATALOG_APP = "launch_catalog_app"


#: run inside the triggering transaction (domain-state changes)
TRANSACTIONAL_ACTION_TYPES: frozenset[TriggerActionType] = frozenset(
    {TriggerActionType.CREATE_EVENT, TriggerActionType.ATTACH_WORKFLOW}
)

#: delivered exactly-once via ``external_action_outbox`` (``action_type`` = value)
OUTBOX_ACTION_TYPES: frozenset[TriggerActionType] = (
    frozenset(TriggerActionType) - TRANSACTIONAL_ACTION_TYPES
)

#: action types the engine (E15-06/08/09) can actually run today. The publish
#: gate (E15-10) refuses a rule whose actions are not all in this set:
#: ``open_camera`` / ``open_camera_group`` / ``integration_action`` need Epic 16,
#: ``launch_catalog_app`` needs the E10 catalog policy.
SUPPORTED_ACTION_TYPES: frozenset[TriggerActionType] = frozenset(
    {
        TriggerActionType.CREATE_EVENT,
        TriggerActionType.ATTACH_WORKFLOW,
        TriggerActionType.SHOW_CLIENT_POPUP,
        TriggerActionType.NOTIFY,
        TriggerActionType.ANSWER_CALL,
        TriggerActionType.SEND_DTMF_PROFILE,
        TriggerActionType.HANGUP_CALL,
    }
)


class UnknownActionTypeError(ValueError):
    """A rule action carried a ``type`` outside :class:`TriggerActionType`."""


def outbox_action_type(raw: str) -> str:
    """Validate ``raw`` is a known outbox-delivered action type; return its value.

    Raises :class:`UnknownActionTypeError` for an unknown type or for a
    transactional type (which never goes through the outbox).
    """
    try:
        action = TriggerActionType(raw)
    except ValueError as exc:
        raise UnknownActionTypeError(raw) from exc
    if action not in OUTBOX_ACTION_TYPES:
        raise UnknownActionTypeError(f"{raw} is not delivered via the outbox")
    return action.value
