"""Normalized telephony event ingestion → inbox → dedupe (E11-03)."""

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

from bbz_core.infra import telephony_ingest
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.telephony_ingest import telephony_dedupe_key


def _event(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "MockAnswered",
        "event_type": "CALL_ANSWERED",
        "source_call_id": "prov-call-1",
        "occurred_at": now,
        "received_at": now,
        "gateway_node": "BBZ-SRV01",
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "telephony-ingest-secret-at-least-32-bytes-!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    telephony_ingest.set_call_event_dispatch(None)
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


async def _inbox_count(s: AsyncSession) -> int:
    """Raw telephony rows only — a call event that maps to an inbound signal also
    queues a ``signal:`` row for the trigger engine (E15-15 / ADR-0024)."""
    return (
        await s.execute(
            select(func.count())
            .select_from(ProviderEventInbox)
            .where(~ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one()


async def _signal_count(s: AsyncSession) -> int:
    return (
        await s.execute(
            select(func.count())
            .select_from(ProviderEventInbox)
            .where(ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one()


# --- unit: the dedupe key ---------------------------------------------------


def test_call_event_dedupes_on_call_and_type_not_event_id() -> None:
    a = _event(telephony_event_id="t-1")
    b = _event(telephony_event_id="t-2")  # replayed after a reconnect
    assert telephony_dedupe_key(a) == telephony_dedupe_key(b)
    assert "prov-call-1" in telephony_dedupe_key(a)


def test_non_call_event_dedupes_on_the_provider_event_id() -> None:
    a = _event(
        event_type="CTI_PROVIDER_OUT_OF_SERVICE", source_call_id=None, telephony_event_id="x1"
    )
    b = _event(
        event_type="CTI_PROVIDER_OUT_OF_SERVICE", source_call_id=None, telephony_event_id="x2"
    )
    assert telephony_dedupe_key(a) != telephony_dedupe_key(b)


# --- API ------------------------------------------------------------------


async def test_new_event_is_ingested_and_dispatched_once(env: tuple) -> None:
    client, s = env
    await _make_user(s, "gw", ["calls.ingest_provider_events"])
    await _login(client, "gw")

    seen: list[str] = []

    async def _dispatch(_session: AsyncSession, ev: dict[str, Any]) -> None:
        seen.append(ev["event_type"])

    telephony_ingest.set_call_event_dispatch(_dispatch)

    r = await client.post("/api/v1/telephony/events", json=_event())
    assert r.status_code == 200 and r.json()["outcome"] == "new"
    assert seen == ["CALL_ANSWERED"]
    assert await _inbox_count(s) == 1
    assert await _signal_count(s) == 1  # queued for the trigger engine (E15-15)


async def test_reconnect_replay_is_a_duplicate(env: tuple) -> None:
    client, s = env
    await _make_user(s, "gw2", ["calls.ingest_provider_events"])
    await _login(client, "gw2")

    dispatched = 0

    async def _dispatch(_session: AsyncSession, _ev: dict[str, Any]) -> None:
        nonlocal dispatched
        dispatched += 1

    telephony_ingest.set_call_event_dispatch(_dispatch)

    first = await client.post("/api/v1/telephony/events", json=_event(telephony_event_id="t-a"))
    # same call + type, different provider event id (the provider replays its backlog)
    again = await client.post("/api/v1/telephony/events", json=_event(telephony_event_id="t-b"))

    assert first.json()["outcome"] == "new"
    assert again.json()["outcome"] == "duplicate"
    assert first.json()["dedupe_key"] == again.json()["dedupe_key"]
    assert dispatched == 1
    assert await _inbox_count(s) == 1


async def test_two_distinct_call_events_both_ingest(env: tuple) -> None:
    client, s = env
    await _make_user(s, "gw3", ["calls.ingest_provider_events"])
    await _login(client, "gw3")
    r1 = await client.post("/api/v1/telephony/events", json=_event(event_type="CALL_RINGING"))
    r2 = await client.post("/api/v1/telephony/events", json=_event(event_type="CALL_ANSWERED"))
    assert r1.json()["outcome"] == r2.json()["outcome"] == "new"
    assert await _inbox_count(s) == 2


@pytest.mark.parametrize(
    "mutate",
    [
        {"event_type": "CALL_SINGING"},  # not in the enum
        {"vendor_specific_field": "JTAPI-42"},  # additionalProperties: false
        {"gateway_node": ""},  # minLength 1
    ],
)
async def test_schema_violation_is_rejected(env: tuple, mutate: dict[str, Any]) -> None:
    client, s = env
    await _make_user(s, "gw4", ["calls.ingest_provider_events"])
    await _login(client, "gw4")
    r = await client.post("/api/v1/telephony/events", json=_event(**mutate))
    assert r.status_code == 422
    assert await _inbox_count(s) == 0


async def test_missing_required_field_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "gw5", ["calls.ingest_provider_events"])
    await _login(client, "gw5")
    bad = _event()
    del bad["telephony_event_id"]
    assert (await client.post("/api/v1/telephony/events", json=bad)).status_code == 422


async def test_ingest_requires_the_machine_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "human", ["calls.view", "calls.answer"])
    await _login(client, "human")
    assert (await client.post("/api/v1/telephony/events", json=_event())).status_code == 403
