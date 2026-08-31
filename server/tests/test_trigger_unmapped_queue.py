"""Unmapped-source queue: a signal that matches no rule is queued (never an
error), deduplicated with a counter, listable, resolvable, counted (E15-12)."""

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
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.unmapped_signals import UnmappedSignal
from bbz_core.infra.repositories.trigger_engine import process_signal

_MANAGE = ["technical_endpoints.view", "technical_endpoints.manage", "door.configure"]

_DOORBELL: dict[str, Any] = {
    "signal_type": "DOORBELL_RINGING",
    "provider": "siedle_mock",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"dnis": "555", "external_source_id": "tor-sued"},
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "unmap-test-secret-at-least-32-bytes-okoko!"
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


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _published_rule(s: AsyncSession, conditions: dict[str, Any]) -> None:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name="r", lifecycle="published", priority=10)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions=conditions,
                actions=[{"type": "notify"}],
            )
        )


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def test_a_signal_with_no_matching_rule_is_queued_not_errored(s: AsyncSession) -> None:
    result = await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")

    assert result.processed and result.matched_rules == 0
    await s.rollback()
    row = (await s.execute(select(UnmappedSignal))).scalars().one()
    assert row.signal_type == "DOORBELL_RINGING" and row.provider == "siedle_mock"
    assert row.source["external_source_id"] == "tor-sued"
    assert row.occurrences == 1 and row.resolved_at is None
    # the inbox row is still marked processed
    assert (await s.execute(select(ProviderEventInbox.processed_at))).scalar_one() is not None


async def test_repeats_from_the_same_source_bump_the_counter(s: AsyncSession) -> None:
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-2")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-3")

    assert await _count(s, UnmappedSignal) == 1
    await s.rollback()
    assert (await s.execute(select(UnmappedSignal.occurrences))).scalar_one() == 3


async def test_a_matched_signal_is_never_queued(s: AsyncSession) -> None:
    await _published_rule(s, {"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]})
    result = await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")

    assert result.matched_rules == 1
    assert await _count(s, UnmappedSignal) == 0


async def test_list_resolve_and_diagnostics_via_the_api(env: tuple) -> None:
    client, s = env
    await _make_user(s, "diag", _MANAGE)
    await _login(client, "diag")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-2")

    listed = await client.get("/api/v1/trigger/unmapped")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    entry = listed.json()[0]
    assert entry["occurrences"] == 2 and entry["signal_type"] == "DOORBELL_RINGING"

    diag = (await client.get("/api/v1/trigger/diagnostics")).json()
    assert diag["unmapped_open"] == 1
    assert diag["total_occurrences"] == 2
    assert diag["open_by_signal_type"] == {"DOORBELL_RINGING": 1}

    # map it to a technical endpoint
    ep = await client.post(
        "/api/v1/technical-endpoints", json={"name": "Tor Süd", "type": "door_station"}
    )
    resolve = await client.post(
        f"/api/v1/trigger/unmapped/{entry['id']}/resolve",
        json={"endpoint_id": ep.json()["id"], "note": "Siedle Tor Süd"},
    )
    assert resolve.status_code == 200
    assert resolve.json()["resolved_at"] is not None
    assert resolve.json()["resolved_endpoint_id"] == ep.json()["id"]

    # drops out of the default list, still visible with include_resolved
    assert (await client.get("/api/v1/trigger/unmapped")).json() == []
    assert len((await client.get("/api/v1/trigger/unmapped?include_resolved=true")).json()) == 1
    diag2 = (await client.get("/api/v1/trigger/diagnostics")).json()
    assert diag2["unmapped_open"] == 0 and diag2["unmapped_resolved"] == 1

    await s.rollback()
    audits = (
        (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "TECHNICAL_ENDPOINT_MAPPED")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1 and audits[0].after["signal_type"] == "DOORBELL_RINGING"


async def test_resolve_with_a_bad_endpoint_id_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "diag2", _MANAGE)
    await _login(client, "diag2")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")
    entry_id = (await client.get("/api/v1/trigger/unmapped")).json()[0]["id"]

    r = await client.post(
        f"/api/v1/trigger/unmapped/{entry_id}/resolve",
        json={"endpoint_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422


async def test_permissions(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["technical_endpoints.view"])
    await _make_user(s, "mgr", _MANAGE)
    await _login(client, "mgr")
    await process_signal(s, signal=_DOORBELL, provider_event_id="evt-1")
    entry_id = (await client.get("/api/v1/trigger/unmapped")).json()[0]["id"]

    await _login(client, "viewer")
    assert (await client.get("/api/v1/trigger/unmapped")).status_code == 200
    assert (await client.get("/api/v1/trigger/diagnostics")).status_code == 200
    assert (
        await client.post(f"/api/v1/trigger/unmapped/{entry_id}/resolve", json={})
    ).status_code == 403
