"""§35 BMA scenario (roadmap E15-13): a call from the configured BMA number
raises exactly one critical event with the current published workflow version
bound and the global priority warning; a duplicate provider event raises no
second event.

No new production code — this proves E15-04/06/09 + E03-15 + E05 compose.
"""

from __future__ import annotations

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
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.infra.repositories.trigger_engine import process_signal

_BMA_NUMBER = "112"
_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "e1", "type": "event"}],
    "edges": [{"key": "a", "from": "e0", "to": "e1"}],
}


def _bma_signal(call_id: str) -> dict[str, Any]:
    return {
        "signal_type": "BMA_ALARM_CALL",
        "provider": "telephony_cucm",
        "occurred_at": "2026-08-31T09:00:00Z",
        "received_at": "2026-08-31T09:00:00Z",
        "gateway_node": "BBZ-SRV01",
        "source": {"dnis": _BMA_NUMBER, "source_call_id": call_id, "direction": "inbound"},
    }


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "bmaflow-test-secret-at-least-32-bytes-ok!!"
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
    if perms:
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
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


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


async def _seed_bma(s: AsyncSession) -> uuid.UUID:
    """BMA endpoint + workflow template (v1 + current v2, both published) + a
    published rule matching the BMA number. Returns the current workflow
    version id (v2)."""
    await s.rollback()
    async with s.begin():
        endpoint = TechnicalEndpoint(
            name="BMA Halle 3", type="bma", site="Nord", default_priority="critical"
        )
        s.add(endpoint)
        await s.flush()
        s.add(TechnicalEndpointNumber(endpoint_id=endpoint.id, called_pattern=_BMA_NUMBER))

        tpl = WorkflowTemplate(key="bma_alarm", name="BMA Alarm")
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="deprecated", definition=_GRAPH
            )
        )
        v2 = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=2, lifecycle="published", definition=_GRAPH
        )
        s.add(v2)

        rule = TriggerRule(
            name="BMA 112 → kritisches Ereignis + EPK",
            endpoint_id=endpoint.id,
            lifecycle="published",
            priority=1,
        )
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "called_number"}, _BMA_NUMBER]},
                actions=[
                    {"type": "create_event", "priority": "critical", "title": "BMA-Alarm Halle 3"},
                    {"type": "attach_workflow", "template_key": "bma_alarm"},
                ],
            )
        )
        await s.flush()
        return v2.id


async def test_bma_call_creates_one_critical_event_with_the_workflow_version_bound(
    s: AsyncSession,
) -> None:
    wf_v2 = await _seed_bma(s)

    result = await process_signal(
        s, signal=_bma_signal("cucm-call-1"), provider_event_id="cti-evt-1"
    )
    assert result.processed and result.matched_rules == 1
    assert [o.action_type for o in result.actions] == ["create_event", "attach_workflow"]

    await s.rollback()
    event = (await s.execute(select(Event))).scalars().one()
    assert event.priority == "critical"
    assert event.status == "new"
    assert event.source == "trigger"
    assert event.title == "BMA-Alarm Halle 3"

    instance = (await s.execute(select(WorkflowInstance))).scalars().one()
    assert instance.event_id == event.id
    assert instance.template_version_id == wf_v2  # the *current* published version

    # visible in the append-only event store
    created = (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "EVENT_CREATED")
            .where(DomainEvent.aggregate_id == str(event.id))
        )
    ).scalar_one()
    assert created == 1
    # both trigger actions audited
    audited = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "TRIGGER_EXECUTED")
        )
    ).scalar_one()
    assert audited == 2


async def test_a_duplicate_bma_provider_event_creates_no_second_event(s: AsyncSession) -> None:
    await _seed_bma(s)

    first = await process_signal(
        s, signal=_bma_signal("cucm-call-1"), provider_event_id="cti-evt-1"
    )
    second = await process_signal(
        s, signal=_bma_signal("cucm-call-1"), provider_event_id="cti-evt-1"
    )

    assert len(first.actions) == 2
    assert second.actions == [] and second.processed
    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1


async def test_the_bma_event_raises_the_priority_alert_until_accepted(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view", "events.accept"])
    await _login(client, "op")
    await _seed_bma(s)

    await process_signal(s, signal=_bma_signal("cucm-call-1"), provider_event_id="cti-evt-1")

    alert = (await client.get("/api/v1/events/priority-alert")).json()
    assert alert["active"] is True
    assert len(alert["events"]) == 1
    ev = alert["events"][0]
    assert ev["priority"] == "critical" and ev["title"] == "BMA-Alarm Halle 3"

    accepted = await client.post(
        f"/api/v1/events/{ev['id']}/accept",
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "1"},
    )
    assert accepted.status_code == 200, accepted.text

    after = (await client.get("/api/v1/events/priority-alert")).json()
    assert after["active"] is False and after["events"] == []


async def test_a_call_to_an_unconfigured_number_creates_no_event(s: AsyncSession) -> None:
    await _seed_bma(s)
    signal = _bma_signal("cucm-call-9")
    signal["source"]["dnis"] = "999"  # not the BMA number

    result = await process_signal(s, signal=signal, provider_event_id="cti-evt-9")

    assert result.matched_rules == 0
    assert await _count(s, Event) == 0
    assert await _count(s, WorkflowInstance) == 0
