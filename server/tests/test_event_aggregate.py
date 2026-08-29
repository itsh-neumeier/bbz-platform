"""Pure event aggregate: transition matrix, emitted events, no-op safety."""

from __future__ import annotations

import uuid

import pytest

from bbz_core.domain.events import (
    EventAggregate,
    EventDomainError,
    EventPriority,
    EventStatus,
    InvalidTransition,
)

ACTOR = uuid.uuid4()


def _agg(status: EventStatus, *, assignee: uuid.UUID | None = None) -> EventAggregate:
    a = EventAggregate(
        id=uuid.uuid4(),
        title="Signalstörung W12",
        priority=EventPriority.HIGH,
        status=status,
        assignee_id=assignee,
    )
    a.collect_events()
    return a


# -- creation ---------------------------------------------------------------


def test_create_starts_new_and_emits_created() -> None:
    a = EventAggregate.create(
        event_id=uuid.uuid4(),
        title="  Weichenstörung  ",
        priority=EventPriority.CRITICAL,
        actor_id=ACTOR,
    )
    assert a.status is EventStatus.NEW
    events = a.collect_events()
    assert [e.type for e in events] == ["EVENT_CREATED"]
    assert events[0].payload["title"] == "Weichenstörung"
    assert events[0].payload["priority"] == "critical"


@pytest.mark.parametrize("title", ["", "   ", "x" * 301])
def test_create_rejects_bad_title(title: str) -> None:
    with pytest.raises(EventDomainError):
        EventAggregate.create(
            event_id=uuid.uuid4(), title=title, priority=EventPriority.LOW, actor_id=ACTOR
        )


# -- happy path -----------------------------------------------------------------


def test_full_lifecycle_emits_expected_events() -> None:
    a = EventAggregate.create(
        event_id=uuid.uuid4(), title="t", priority=EventPriority.MEDIUM, actor_id=ACTOR
    )
    a.collect_events()

    a.accept(ACTOR)
    a.acknowledge(ACTOR)
    a.open(ACTOR)
    a.archive(ACTOR, reason="Feierabend, nichts offen")
    a.reactivate(ACTOR, reason="Rückfrage der Leitstelle")

    assert a.status is EventStatus.OPENED
    assert [e.type for e in a.collect_events()] == [
        "EVENT_ACCEPTED",
        "EVENT_ACKNOWLEDGED",
        "EVENT_OPENED",
        "EVENT_ARCHIVED",
        "EVENT_REACTIVATED",
    ]


# -- field edit ---------------------------------------------------------------


def test_update_records_before_and_after() -> None:
    a = _agg(EventStatus.ACCEPTED)
    a.update(actor_id=ACTOR, title="Neuer Titel", priority=EventPriority.CRITICAL)
    assert a.title == "Neuer Titel"
    assert a.priority is EventPriority.CRITICAL
    ev = a.collect_events()
    assert [e.type for e in ev] == ["EVENT_UPDATED"]
    assert ev[0].payload["changes"]["title"]["to"] == "Neuer Titel"
    assert ev[0].payload["changes"]["priority"] == {"from": "high", "to": "critical"}


def test_update_with_no_effective_change_is_rejected() -> None:
    a = _agg(EventStatus.ACCEPTED)
    with pytest.raises(EventDomainError):
        a.update(actor_id=ACTOR)  # nothing supplied
    with pytest.raises(EventDomainError):
        a.update(actor_id=ACTOR, title="Signalstörung W12")  # same value
    assert a.collect_events() == []


def test_update_blocked_on_archived() -> None:
    a = _agg(EventStatus.ARCHIVED)
    with pytest.raises(InvalidTransition):
        a.update(actor_id=ACTOR, title="x")


# -- invalid transitions -------------------------------------------------------

_LIFECYCLE_CALLS = {
    "accept": (lambda a: a.accept(ACTOR), {EventStatus.NEW}),
    "acknowledge": (lambda a: a.acknowledge(ACTOR), {EventStatus.ACCEPTED}),
    "open": (lambda a: a.open(ACTOR), {EventStatus.ACKNOWLEDGED}),
    "archive": (lambda a: a.archive(ACTOR, reason="r"), {EventStatus.OPENED}),
    "reactivate": (lambda a: a.reactivate(ACTOR, reason="r"), {EventStatus.ARCHIVED}),
}


@pytest.mark.parametrize("name", list(_LIFECYCLE_CALLS))
@pytest.mark.parametrize("status", list(EventStatus))
def test_transition_matrix(name: str, status: EventStatus) -> None:
    call, valid_from = _LIFECYCLE_CALLS[name]
    a = _agg(status)

    if status in valid_from:
        call(a)
        assert a.collect_events()  # produced at least one event
        assert a.status is not status  # status advanced
    else:
        with pytest.raises(InvalidTransition):
            call(a)
        assert a.status is status
        assert a.collect_events() == []  # nothing emitted on a rejected transition


# -- ownership ----------------------------------------------------------------


def test_assign_reassign_and_take_over() -> None:
    u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = _agg(EventStatus.ACCEPTED)

    a.assign(to_user_id=u1, actor_id=ACTOR)
    assert a.assignee_id == u1
    assert [e.type for e in a.collect_events()] == ["EVENT_ASSIGNED"]

    with pytest.raises(EventDomainError):
        a.assign(to_user_id=u1, actor_id=ACTOR)  # no change
    assert a.collect_events() == []

    a.assign(to_user_id=u2, actor_id=ACTOR)  # reassignment is allowed
    ev = a.collect_events()
    assert [e.type for e in ev] == ["EVENT_ASSIGNED"]
    assert ev[0].payload == {
        "from_user_id": str(u1),
        "to_user_id": str(u2),
        "actor_id": str(ACTOR),
    }

    a.take_over(new_user_id=u3, actor_id=ACTOR)
    assert a.assignee_id == u3
    ev = a.collect_events()
    assert [e.type for e in ev] == ["EVENT_TAKEN_OVER"]
    assert ev[0].payload["from_user_id"] == str(u2)


def test_take_over_requires_existing_owner_and_a_change() -> None:
    a = _agg(EventStatus.ACCEPTED)
    with pytest.raises(EventDomainError):
        a.take_over(new_user_id=uuid.uuid4(), actor_id=ACTOR)

    u1 = uuid.uuid4()
    a.assign(to_user_id=u1, actor_id=ACTOR)
    a.collect_events()
    with pytest.raises(EventDomainError):
        a.take_over(new_user_id=u1, actor_id=ACTOR)  # no actual change


def test_assign_blocked_on_archived() -> None:
    with pytest.raises(InvalidTransition):
        _agg(EventStatus.ARCHIVED).assign(to_user_id=uuid.uuid4(), actor_id=ACTOR)


def test_take_over_blocked_on_archived() -> None:
    a = _agg(EventStatus.ARCHIVED, assignee=uuid.uuid4())
    with pytest.raises(InvalidTransition):
        a.take_over(new_user_id=uuid.uuid4(), actor_id=ACTOR)


# -- reason requirements ------------------------------------------------------


def test_archive_and_reactivate_need_a_reason() -> None:
    a = _agg(EventStatus.OPENED)
    with pytest.raises(EventDomainError):
        a.archive(ACTOR, reason="   ")
    assert a.status is EventStatus.OPENED

    b = _agg(EventStatus.ARCHIVED)
    with pytest.raises(EventDomainError):
        b.reactivate(ACTOR, reason="")
    assert b.status is EventStatus.ARCHIVED


def test_no_event_is_emitted_without_a_state_change() -> None:
    # exhaustively: any rejected call leaves pending empty
    for status in EventStatus:
        for name, (call, valid_from) in _LIFECYCLE_CALLS.items():
            if status in valid_from:
                continue
            a = _agg(status)
            with pytest.raises(EventDomainError):
                call(a)
            assert a.collect_events() == [], (name, status)
