"""Function-node task-kind classification helpers (E05-10)."""

from __future__ import annotations

import uuid

import pytest

from bbz_core.domain.workflow.tasks import (
    AUTO_KINDS,
    OPERATOR_KINDS,
    TIMER_KINDS,
    TaskKindError,
    outbox_action,
    step_dedupe_key,
    timer_seconds,
)


def test_the_kind_sets_are_disjoint_and_cover_the_schema() -> None:
    assert OPERATOR_KINDS.isdisjoint(AUTO_KINDS)
    assert TIMER_KINDS.isdisjoint(AUTO_KINDS | OPERATOR_KINDS)
    all_kinds = OPERATOR_KINDS | TIMER_KINDS | AUTO_KINDS
    assert all_kinds == {
        "manual",
        "confirmation",
        "documentation",
        "timer",
        "integration_action",
        "notification",
        "event_update",
    }


def test_outbox_action_maps_each_auto_kind() -> None:
    assert outbox_action("notification") == "notify"
    assert outbox_action("integration_action") == "integration"
    assert outbox_action("event_update") == "event_update"


def test_outbox_action_rejects_a_non_auto_kind() -> None:
    with pytest.raises(TaskKindError):
        outbox_action("manual")


def test_timer_seconds_reads_props_with_a_default() -> None:
    assert timer_seconds({"duration_seconds": 30}) == 30
    assert timer_seconds({"duration_seconds": "45"}) == 45
    assert timer_seconds(None) == 60
    assert timer_seconds({}) == 60


@pytest.mark.parametrize("bad", [{"duration_seconds": "soon"}, {"duration_seconds": -1}])
def test_timer_seconds_rejects_bad_values(bad: dict[str, object]) -> None:
    with pytest.raises(TaskKindError):
        timer_seconds(bad)


def test_step_dedupe_key_is_stable_and_scoped() -> None:
    iid = uuid.uuid4()
    assert step_dedupe_key(iid, "n1") == f"workflow-step:{iid}:n1:attempt-0"
    assert step_dedupe_key(iid, "n1") != step_dedupe_key(iid, "n2")
