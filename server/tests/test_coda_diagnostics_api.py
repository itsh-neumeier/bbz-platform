"""GET /api/v1/integrations/coda_video/diagnostics (roadmap E16-10): the admin
view aggregates the provider inbox / outbox + the provider's own health; it needs
`integrations.diagnostics` and carries no secrets.
"""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.alarm_ingest import ingest_alarm_event
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.outbox import enqueue
from bbz_core.infra.repositories.trigger_engine import TriggerEngine

_SOURCE = "CODA-ALARM-4711"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "coda-diag-test-secret-at-least-32-bytes-x!"
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


def _alarm(event_id: str = "CODA-EVT-1", *, source: str = _SOURCE) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    return {
        "provider": "coda_video",
        "provider_instance_id": "coda-mock-1",
        "provider_event_id": event_id,
        "alarm_type": "panic",
        "alarm_subtype": "panic_button",
        "source_external_id": source,
        "received_at": now,
        "occurred_at": now,
        "raw": {"id": event_id},
    }


async def _publish_rule(s: AsyncSession) -> None:
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Panik",
            type="panic_button",
            provider_id="coda_video",
            external_source_ids=[_SOURCE],
        )
        s.add(ep)
        await s.flush()
        rule = TriggerRule(name="Panik", endpoint_id=ep.id, lifecycle="published", priority=1)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "external_source_id"}, _SOURCE]},
                actions=[{"type": "create_event", "priority": "critical", "title": "Panik"}],
            )
        )


async def test_diagnostics_needs_the_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d0", ["technical_endpoints.view"])
    await _login(client, "d0")
    r = await client.get("/api/v1/integrations/coda_video/diagnostics")
    assert r.status_code == 403


async def test_empty_diagnostics_reports_zeroes_and_provider_health(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d1", ["integrations.diagnostics"])
    await _login(client, "d1")

    body = (await client.get("/api/v1/integrations/coda_video/diagnostics")).json()
    assert body["integration_id"] == "coda_video"
    assert body["events_total"] == 0 and body["signals_total"] == 0
    assert body["unmapped_total"] == 0
    assert body["last_event_at"] is None and body["last_camera_action_at"] is None
    assert body["camera_actions_failed"] == 0 and body["camera_actions_pending"] == 0
    assert body["health"]["state"] == "healthy"
    assert "video.open_camera" in body["capabilities"]
    assert "secret" not in str(body).lower() and "password" not in str(body).lower()


async def test_diagnostics_reflect_ingested_alarms_and_camera_actions(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d2", ["integrations.diagnostics"])
    await _login(client, "d2")
    await _publish_rule(s)

    async with s.begin():
        await ingest_alarm_event(s, _alarm("CODA-EVT-1"))
    await s.rollback()
    await TriggerEngine(s).resume_unprocessed()

    # an unmapped alarm from another source
    async with s.begin():
        await ingest_alarm_event(s, _alarm("CODA-EVT-2", source="OTHER-SRC"))
    await s.rollback()
    await TriggerEngine(s).resume_unprocessed()

    # a dispatched + a failed camera action
    async with s.begin():
        await enqueue(
            s,
            dedupe_key="cam-ok",
            action_type="open_camera_group",
            payload={"camera_refs": ["C1"], "command_id": "x"},
        )
        await enqueue(
            s,
            dedupe_key="cam-bad",
            action_type="open_camera",
            payload={"camera_ref": "C2", "command_id": "y"},
        )
    async with s.begin():
        rows = (await s.execute(select(ExternalActionOutbox))).scalars().all()
        for row in rows:
            row.status = "dispatched" if row.dedupe_key == "cam-ok" else "failed"
            if row.dedupe_key == "cam-ok":
                row.dispatched_at = _dt.datetime.now(_dt.UTC)

    body = (await client.get("/api/v1/integrations/coda_video/diagnostics")).json()
    assert body["events_total"] == 2  # both alarms persisted
    assert body["signals_total"] == 2
    assert body["last_event_at"] is not None
    assert body["last_event_processing_ms"] is not None and body["last_event_processing_ms"] >= 0
    assert body["unmapped_total"] == 1  # only the OTHER-SRC one had no rule
    assert body["last_camera_action_at"] is not None
    assert body["camera_actions_failed"] == 1
