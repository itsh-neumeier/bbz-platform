"""GET /calls/ringing — the waiting-call queue, priority-sorted (E11-12)."""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


def _ev(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "Mock",
        "event_type": "CALL_RINGING",
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
    os.environ["BBZ_JWT_SECRET"] = "call-queue-secret-at-least-32-bytes-okok!!"
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
        p = Permission(key=key, area=key.split(".")[0])
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


async def _contact(s: AsyncSession, name: str, e164: str, priority: str) -> uuid.UUID:
    from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority

    c = Contact(name=name)
    s.add(c)
    await s.flush()
    s.add(ContactNumber(contact_id=c.id, e164=e164, is_primary=True))
    s.add(ContactPriority(contact_id=c.id, priority=priority))
    cid = c.id
    await s.commit()
    return cid


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", ["calls.view", "calls.ingest_provider_events", "calls.answer"])
    await _make_user(s, "nobody", [])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "op", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    yield client, s


async def _ring(client: httpx.AsyncClient, source_call_id: str, calling_number: str) -> None:
    r = await client.post(
        "/api/v1/telephony/events",
        json=_ev(source_call_id=source_call_id, calling_number=calling_number, called_number="110"),
    )
    assert r.status_code == 200, r.text


async def _queue(client: httpx.AsyncClient) -> list[dict]:
    r = await client.get("/api/v1/calls/ringing")
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def test_queue_is_ordered_high_to_low_then_unknown_last(env: tuple) -> None:
    client, s = env
    await _contact(s, "Wichtig", "+49911100001", "high")
    await _contact(s, "Mittel", "+49911100002", "medium")
    await _contact(s, "Klein", "+49911100003", "low")

    await _ring(client, "c-low", "+49911100003")
    await _ring(client, "c-unknown", "+49911999999")
    await _ring(client, "c-high", "+49911100001")
    await _ring(client, "c-medium", "+49911100002")

    q = await _queue(client)
    assert [c["caller_priority"] for c in q] == ["high", "medium", "low", None]
    assert all(c["state"] == "ringing" for c in q)


async def test_same_priority_is_ordered_longest_waiting_first(env: tuple) -> None:
    client, s = env
    await _contact(s, "A", "+49911100001", "high")
    await _contact(s, "B", "+49911100002", "high")

    await _ring(client, "c-first", "+49911100001")
    await asyncio.sleep(0.05)
    await _ring(client, "c-second", "+49911100002")

    q = await _queue(client)
    assert [c["caller_priority"] for c in q] == ["high", "high"]
    # the call that has been waiting longer comes first
    first_started = q[0]["created_at"]
    second_started = q[1]["created_at"]
    assert first_started < second_started


async def test_answered_and_ended_calls_leave_the_queue(env: tuple) -> None:
    client, s = env
    await _contact(s, "Hoch", "+49911100001", "high")
    await _ring(client, "c-1", "+49911100001")
    await _ring(client, "c-2", "+49911999999")
    assert len(await _queue(client)) == 2

    await client.post(
        "/api/v1/telephony/events",
        json=_ev(source_call_id="c-1", event_type="CALL_ANSWERED", calling_number="+49911100001"),
    )
    await client.post(
        "/api/v1/telephony/events",
        json=_ev(
            source_call_id="c-2", event_type="CALL_DISCONNECTED", calling_number="+49911999999"
        ),
    )

    assert await _queue(client) == []


async def test_queue_items_carry_the_caller_resolution(env: tuple) -> None:
    client, s = env
    cid = await _contact(s, "EVU Leitstelle", "+49911100001", "high")
    await _ring(client, "c-1", "0911 100 001")

    (item,) = await _queue(client)
    assert item["caller_contact_id"] == str(cid)
    assert item["caller_priority"] == "high"
    assert item["state"] == "ringing"


async def test_queue_requires_calls_view(env: tuple) -> None:
    client, _ = env
    r = await client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/calls/ringing")).status_code == 403


async def test_ingesting_a_new_call_event_wakes_the_event_stream(env: tuple) -> None:
    from bbz_core.infra import event_stream

    client, _ = env
    woken = asyncio.Event()

    async def _watch() -> None:
        await event_stream.get_broker().wait(timeout=5.0)
        woken.set()

    task = asyncio.create_task(_watch())
    await asyncio.sleep(0.05)
    await _ring(client, "c-wake", "+49911999999")
    await asyncio.wait_for(woken.wait(), timeout=2.0)
    await task
