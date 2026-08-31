"""§36.1 "Überfallalarm" end-to-end (roadmap E16-11).

The full 10-step scenario over the compose stack + the E16-09 ``coda_video`` mock:
a panic alarm is persisted and deduplicated, the endpoint mapping resolves, the
trigger engine raises exactly one critical event with the current published EPK
version bound plus a client popup and the priority warning, the camera group is
dispatched as a decoupled outbox side effect, a camera failure is tolerated, and
a duplicate alarm or an SRV01-crash replay over SRV02 creates no second event.

No new production code — proves E16-04/07/08/09 + E15-06/07/09 compose under the
HA rules (ADR-0006).
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

from bbz_core.infra.alarm_ingest import ingest_alarm_event
from bbz_core.infra.db import get_sessionmaker
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.integrations_host.providers import reset_provider_cache
from bbz_core.workers import camera_handlers
from bbz_core.workers.registry import cluster_singletons
from integrations.coda_video.adapter import MockCodaVideoProvider

_SOURCE = "CODA-ALARM-4711"
_WORKPLACE = "22222222-2222-2222-2222-222222222222"
_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "e1", "type": "event"}],
    "edges": [{"key": "a", "from": "e0", "to": "e1"}],
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "e2e-coda-secret-at-least-32-bytes-okokok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture(autouse=True)
def _clean_provider_cache() -> Iterator[None]:
    reset_provider_cache()
    yield
    reset_provider_cache()


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


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def _trigger_tick() -> int:
    tick = next(spec.tick for spec in cluster_singletons() if spec.name == "trigger-engine")
    result = await tick()
    assert isinstance(result, int)
    return result


async def _outbox_tick() -> int:
    tick = next(spec.tick for spec in cluster_singletons() if spec.name == "outbox-dispatcher")
    result = await tick()
    assert isinstance(result, int)
    return result


async def _seed(s: AsyncSession) -> uuid.UUID:
    """coda_video panic endpoint + workflow (v1 deprecated, v2 published) + a
    published rule matching the source. Returns the current published version."""
    await s.rollback()
    async with s.begin():
        endpoint = TechnicalEndpoint(
            name="Ueberfalltaster SP Nbg",
            type="panic_button",
            site="Nuernberg Hbf",
            provider_id="coda_video",
            external_source_ids=[_SOURCE],
            default_priority="critical",
        )
        s.add(endpoint)
        await s.flush()

        tpl = WorkflowTemplate(key="ueberfall", name="Ueberfall ServicePoint")
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
            name="Coda Panik SP Nbg", endpoint_id=endpoint.id, lifecycle="published", priority=1
        )
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "external_source_id"}, _SOURCE]},
                actions=[
                    {
                        "type": "create_event",
                        "priority": "critical",
                        "title": "Ueberfall SP Nuernberg",
                    },
                    {"type": "attach_workflow", "template_key": "ueberfall"},
                    {"type": "show_client_popup", "workplace_id": _WORKPLACE, "kind": "panic"},
                    {
                        "type": "open_camera_group",
                        "camera_refs": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
                    },
                ],
            )
        )
        await s.flush()
        return v2.id


def _mock_provider(event_id: str = "CODA-EVT-1") -> MockCodaVideoProvider:
    p = MockCodaVideoProvider(
        simulated_sources=[
            {"external_source_id": _SOURCE, "name": "SP Nbg", "cameras": ["CAM-SP-NBG-01"]}
        ]
    )
    p.simulate_alarm(
        {
            "id": event_id,
            "source": _SOURCE,
            "type": "panic",
            "subtype": "panic_button",
            "severity": "critical",
            "site": "Nuernberg Hbf",
            "cameras": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
        }
    )
    return p


async def test_36_1_ueberfallalarm_end_to_end(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view", "events.accept"])
    wf_v2 = await _seed(s)

    # (1) the Coda mock emits a panic alarm; (2) it is persisted + deduplicated
    provider = _mock_provider("CODA-EVT-1")
    alarms = [a async for a in provider.subscribe_alarms()]
    async with s.begin():
        result = await ingest_alarm_event(s, alarms[0].model_dump(mode="json"))
    assert result.outcome.value == "new"

    # (3) endpoint mapping resolves; (4)(5)(6) the engine raises exactly one
    #     critical event with the current published EPK version + a popup
    assert await _trigger_tick() >= 1
    await s.rollback()
    event = (await s.execute(select(Event))).scalars().one()
    event_id = event.id
    assert event.priority == "critical" and event.status == "new" and event.source == "trigger"
    instance = (await s.execute(select(WorkflowInstance))).scalars().one()
    assert instance.event_id == event_id and instance.template_version_id == wf_v2
    popup = (await s.execute(select(ClientPopupEvent))).scalars().one()
    assert str(popup.workplace_id) == _WORKPLACE
    assert (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "CLIENT_POPUP_RAISED")
        )
    ).scalar_one() == 1

    # (7) the priority warning is active until an operator accepts
    await _login(client, "op")
    alert = (await client.get("/api/v1/events/priority-alert")).json()
    assert alert["active"] is True and len(alert["events"]) == 1
    assert alert["events"][0]["priority"] == "critical"

    # (8) the camera group is dispatched as a decoupled outbox side effect
    assert await _outbox_tick() >= 1
    await s.rollback()
    cam = (
        (
            await s.execute(
                select(ExternalActionOutbox).where(
                    ExternalActionOutbox.action_type == "open_camera_group"
                )
            )
        )
        .scalars()
        .one()
    )
    assert cam.status == "dispatched"
    assert cam.result["camera_ids"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]

    # audits: one TRIGGER_EXECUTED per action, one EXTERNAL_ACTION_DISPATCHED
    assert await _audit_count(s, "TRIGGER_EXECUTED") == 4
    assert await _audit_count(s, "EXTERNAL_ACTION_DISPATCHED") == 1

    # (10) SRV01 "crash": the signal row is re-drained by SRV02 as if unprocessed;
    #      the trigger_executions claims make every action a no-op
    await s.rollback()
    async with s.begin():
        row = (
            await s.execute(
                select(ProviderEventInbox).where(ProviderEventInbox.dedupe_key.like("signal:%"))
            )
        ).scalar_one()
        row.processed_at = None
    assert await _trigger_tick() >= 1
    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1
    assert await _count(s, ClientPopupEvent) == 1

    # a duplicate provider alarm (same id) creates nothing new
    await s.rollback()
    async with s.begin():
        dup = await ingest_alarm_event(s, _mock_alarm_dict("CODA-EVT-1"))
    assert dup.outcome.value == "duplicate"
    await _trigger_tick()
    assert await _count(s, Event) == 1

    # the operator accepts -> the priority warning clears
    ev_id = alert["events"][0]["id"]
    accepted = await client.post(
        f"/api/v1/events/{ev_id}/accept",
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "1"},
    )
    assert accepted.status_code == 200, accepted.text
    assert (await client.get("/api/v1/events/priority-alert")).json()["active"] is False


def _mock_alarm_dict(event_id: str) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    return {
        "provider": "coda_video",
        "provider_instance_id": "coda-mock-1",
        "provider_event_id": event_id,
        "alarm_type": "panic",
        "alarm_subtype": "panic_button",
        "source_external_id": _SOURCE,
        "site_external_id": "Nuernberg Hbf",
        "occurred_at": now,
        "received_at": now,
        "severity_external": "critical",
        "associated_camera_ids": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
        "raw": {"id": event_id},
    }


async def test_a_camera_failure_is_tolerated_and_noted_on_the_event(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, s = env
    await _seed(s)

    # the video provider fails every camera open
    failing = MockCodaVideoProvider(camera_failures=["CAM-SP-NBG-01", "CAM-SP-NBG-02"])

    async def _failing_provider() -> Any:
        return failing

    monkeypatch.setattr(camera_handlers, "active_video_provider", _failing_provider)

    async with s.begin():
        await ingest_alarm_event(s, _mock_alarm_dict("CODA-EVT-9"))
    await _trigger_tick()
    await s.rollback()
    event_id = (await s.execute(select(Event.id))).scalar_one()

    # drive the camera outbox row to its terminal failure
    for _ in range(20):
        async with get_sessionmaker()() as w, w.begin():
            row = (
                await w.execute(
                    select(ExternalActionOutbox).where(
                        ExternalActionOutbox.action_type == "open_camera_group"
                    )
                )
            ).scalar_one()
            if row.status == "failed":
                break
            row.next_attempt_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=1)
        await _outbox_tick()

    await s.rollback()
    row = (
        (
            await s.execute(
                select(ExternalActionOutbox).where(
                    ExternalActionOutbox.action_type == "open_camera_group"
                )
            )
        )
        .scalars()
        .one()
    )
    assert row.status == "failed"

    # the event is untouched and still active; the failure is noted on it
    fresh = (await s.execute(select(Event).where(Event.id == event_id))).scalars().one()
    assert fresh.status == "new" and fresh.priority == "critical"
    notes = (
        (
            await s.execute(
                select(DomainEvent).where(DomainEvent.event_type == "CAMERA_ACTION_FAILED")
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) == 1 and notes[0].aggregate_id == str(event_id)
    assert await _audit_count(s, "EXTERNAL_ACTION_FAILED") == 1
