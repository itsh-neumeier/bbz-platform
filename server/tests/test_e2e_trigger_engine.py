"""End-to-end trigger engine (roadmap E15-15, ADR-0024): a telephony call to the
configured BMA number is ingested, queued as an inbound signal, drained by the
`trigger-engine` worker tick into exactly one critical event + bound workflow,
and a duplicate provider event or a failover replay produces no second event.

API-level walk (the browser layer over Compose is a separate Playwright issue),
same style as `test_e2e_archive_lifecycle.py`.
"""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.workers.registry import cluster_singletons

_BMA_NUMBER = "112"
_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "e1", "type": "event"}],
    "edges": [{"key": "a", "from": "e0", "to": "e1"}],
}


def _call_event(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": kw.pop("telephony_event_id", f"t-{uuid.uuid4().hex[:10]}"),
        "provider": "telephony_mock",
        "raw_event_type": "Mock",
        "event_type": "CALL_RINGING",
        "occurred_at": now,
        "received_at": now,
        "gateway_node": "BBZ-SRV01",
        "source_call_id": "cucm-call-1",
        "called_number": _BMA_NUMBER,
        "calling_number": "+49110",
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "e2e-trig-secret-at-least-32-bytes-okokok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key=f"r-{username}", name="R")
    s.add(role)
    await s.flush()
    for key in perms:
        pid = (
            await s.execute(select(Permission.id).where(Permission.key == key))
        ).scalar_one_or_none()
        if pid is None:
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            pid = p.id
        s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _trigger_tick() -> int:
    tick = next(spec.tick for spec in cluster_singletons() if spec.name == "trigger-engine")
    result = await tick()
    assert isinstance(result, int)
    return result


async def _seed(s: AsyncSession) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        tpl = WorkflowTemplate(key="bma_alarm", name="BMA Alarm")
        s.add(tpl)
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
        )
        s.add(v)
        rule = TriggerRule(name="BMA 112 Anruf", lifecycle="published", priority=1)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={
                    "op": "and",
                    "args": [
                        {"op": "eq", "args": [{"field": "signal_type"}, "CALL_RINGING"]},
                        {"op": "eq", "args": [{"field": "called_number"}, _BMA_NUMBER]},
                    ],
                },
                actions=[
                    {"type": "create_event", "priority": "critical", "title": "BMA-Alarm"},
                    {"type": "attach_workflow", "template_key": "bma_alarm"},
                ],
            )
        )
        await s.flush()
        return v.id


async def test_bma_call_ingest_to_event_via_the_drain_worker(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _make_user(s, "op", ["events.view"])
    wf_v1 = await _seed(s)

    await _login(client, "cti")
    ingest = await client.post("/api/v1/telephony/events", json=_call_event())
    assert ingest.status_code == 200 and ingest.json()["outcome"] == "new"

    # the signal is queued but the engine has not run yet
    await s.rollback()
    signal_rows = (
        (
            await s.execute(
                select(ProviderEventInbox).where(ProviderEventInbox.dedupe_key.like("signal:%"))
            )
        )
        .scalars()
        .all()
    )
    assert len(signal_rows) == 1 and signal_rows[0].processed_at is None
    assert await _count(s, Event) == 0

    # the trigger-engine tick drains it
    assert await _trigger_tick() == 1

    await s.rollback()
    event = (await s.execute(select(Event))).scalars().one()
    assert event.priority == "critical" and event.source == "trigger" and event.status == "new"
    instance = (await s.execute(select(WorkflowInstance))).scalars().one()
    assert instance.event_id == event.id and instance.template_version_id == wf_v1
    assert (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "EVENT_CREATED")
        )
    ).scalar_one() == 1
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "TRIGGER_EXECUTED")
        )
    ).scalar_one() == 2

    # a second tick with nothing queued is a no-op
    assert await _trigger_tick() == 0
    assert await _count(s, Event) == 1


async def test_a_duplicate_provider_event_produces_no_second_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _seed(s)
    await _login(client, "cti")

    ev = _call_event(telephony_event_id="t-fixed-1")
    first = await client.post("/api/v1/telephony/events", json=ev)
    assert first.json()["outcome"] == "new"
    await _trigger_tick()

    # the provider replays the exact same event
    dup = await client.post("/api/v1/telephony/events", json=ev)
    assert dup.json()["outcome"] == "duplicate"
    assert await _trigger_tick() == 0  # no new signal row was queued

    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1


async def test_a_failover_replay_of_a_processed_signal_does_not_duplicate(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _seed(s)
    await _login(client, "cti")

    await client.post("/api/v1/telephony/events", json=_call_event())
    await _trigger_tick()
    assert await _count(s, Event) == 1

    # a new leader re-drains a row it believes is unprocessed (crash before the
    # mark committed): the trigger_executions claims make every action a no-op
    await s.rollback()
    async with s.begin():
        row = (
            await s.execute(
                select(ProviderEventInbox).where(ProviderEventInbox.dedupe_key.like("signal:%"))
            )
        ).scalar_one()
        row.processed_at = None

    assert await _trigger_tick() == 1
    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1
