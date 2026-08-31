"""Typed trigger-action vocabulary (E15-03) — pure, no database."""

from __future__ import annotations

import pytest

from bbz_core.domain.triggers import (
    OUTBOX_ACTION_TYPES,
    TRANSACTIONAL_ACTION_TYPES,
    TriggerActionType,
    outbox_action_type,
)
from bbz_core.domain.triggers.actions import UnknownActionTypeError

# the six action types E15-03 names as outbox-delivered, plus the rest
_ROADMAP_OUTBOX = {
    "open_camera",
    "answer_call",
    "send_dtmf_profile",
    "hangup_call",
    "show_client_popup",
    "notify",
}


def test_all_technical_triggers_action_types_are_declared() -> None:
    declared = {a.value for a in TriggerActionType}
    assert declared >= _ROADMAP_OUTBOX
    assert {
        "create_event",
        "attach_workflow",
        "integration_action",
        "open_camera_group",
        "launch_catalog_app",
    } <= declared


def test_transactional_and_outbox_sets_partition_the_enum() -> None:
    assert set(TriggerActionType) == TRANSACTIONAL_ACTION_TYPES | OUTBOX_ACTION_TYPES
    assert set() == TRANSACTIONAL_ACTION_TYPES & OUTBOX_ACTION_TYPES
    assert {
        TriggerActionType.CREATE_EVENT,
        TriggerActionType.ATTACH_WORKFLOW,
    } == TRANSACTIONAL_ACTION_TYPES
    assert {a.value for a in OUTBOX_ACTION_TYPES} >= _ROADMAP_OUTBOX


@pytest.mark.parametrize("raw", sorted(_ROADMAP_OUTBOX))
def test_outbox_action_type_accepts_known_outbox_actions(raw: str) -> None:
    assert outbox_action_type(raw) == raw


@pytest.mark.parametrize("raw", ["create_event", "attach_workflow"])
def test_transactional_actions_are_not_outbox_actions(raw: str) -> None:
    with pytest.raises(UnknownActionTypeError, match="not delivered via the outbox"):
        outbox_action_type(raw)


def test_an_unknown_action_type_is_rejected() -> None:
    with pytest.raises(UnknownActionTypeError):
        outbox_action_type("rm_-rf_slash")
