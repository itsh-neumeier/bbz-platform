"""Hangup guard: no call is closed without a documentation category (E11-10)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.telephony import Call

_ALL = ["calls.answer", "calls.hangup", "calls.document", "calls.view"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "hangup-guard-secret-at-least-32-bytes-okok!!"
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
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, uuid.UUID]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", _ALL)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "op", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200

    from bbz_core.integrations_host.providers import active_telephony_provider

    provider = await active_telephony_provider()
    scid = provider.simulate_incoming(from_number="+49911500", to_line="1001")  # type: ignore[attr-defined]

    call = Call(
        bbz_call_id=f"CALL-{uuid.uuid4().hex[:8]}",
        provider="telephony_mock",
        source_call_id=scid,
        direction="inbound",
        state="connected",
    )
    s.add(call)
    await s.flush()
    cid = call.id
    await s.commit()
    yield client, s, cid


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def _state(s: AsyncSession, cid: uuid.UUID) -> str:
    await s.rollback()
    return (await s.execute(select(Call.state).where(Call.id == cid))).scalar_one()


async def _call_events(s: AsyncSession, cid: uuid.UUID) -> list[str]:
    await s.rollback()
    return [
        r.event_type
        for r in (
            await s.execute(
                select(DomainEvent)
                .where(DomainEvent.aggregate_id == str(cid))
                .order_by(DomainEvent.event_seq.asc())
            )
        ).scalars()
    ]


async def test_hangup_without_a_category_leaves_the_call_pending(env: tuple) -> None:
    client, s, cid = env
    r = await client.post(f"/api/v1/calls/{cid}/hangup", headers=_cmd())
    assert r.status_code == 200 and r.json()["detail"] == "pending documentation"

    assert await _state(s, cid) == "ended_pending_documentation"
    assert "CALL_ENDED" not in await _call_events(s, cid)

    pending = (await client.get("/api/v1/calls/pending-documentation")).json()["calls"]
    assert [p["call_id"] for p in pending] == [str(cid)]


async def test_documenting_a_pending_call_closes_it(env: tuple) -> None:
    client, s, cid = env
    await client.post(f"/api/v1/calls/{cid}/hangup", headers=_cmd())

    r = await client.put(f"/api/v1/calls/{cid}/documentation", json={"category": "technical_fault"})
    assert r.status_code == 200

    assert await _state(s, cid) == "disconnected"
    events = await _call_events(s, cid)
    assert events == ["CALL_DOCUMENTED", "CALL_ENDED"]

    pending = (await client.get("/api/v1/calls/pending-documentation")).json()["calls"]
    assert pending == []


async def test_hangup_with_a_category_already_set_closes_immediately(env: tuple) -> None:
    client, s, cid = env
    await client.put(f"/api/v1/calls/{cid}/documentation", json={"category": "other"})

    r = await client.post(f"/api/v1/calls/{cid}/hangup", headers=_cmd())
    assert r.status_code == 200 and r.json()["detail"] == "closed"
    assert await _state(s, cid) == "disconnected"
    assert (await client.get("/api/v1/calls/pending-documentation")).json()["calls"] == []
    assert "CALL_ENDED" in await _call_events(s, cid)


async def test_pending_documentation_list_requires_calls_document(env: tuple) -> None:
    client, s, cid = env
    await client.post(f"/api/v1/calls/{cid}/hangup", headers=_cmd())

    await _make_user(s, "weak", ["calls.view"])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "weak", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/calls/pending-documentation")).status_code == 403


async def test_free_text_only_does_not_close_a_pending_call(env: tuple) -> None:
    client, s, cid = env
    await client.post(f"/api/v1/calls/{cid}/hangup", headers=_cmd())
    r = await client.put(f"/api/v1/calls/{cid}/documentation", json={"free_text": "kein Kategorie"})
    assert r.status_code == 200
    assert await _state(s, cid) == "ended_pending_documentation"  # still open
