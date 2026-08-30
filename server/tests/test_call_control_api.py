"""Call control API — provider translation, idempotency, permissions (E11-06)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.telephony import Call

_ALL = ["calls.answer", "calls.dial", "calls.hangup", "calls.hold", "calls.transfer", "calls.view"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "call-control-secret-at-least-32-bytes-okay!!"
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


def _cmd(command_id: uuid.UUID | None = None) -> dict[str, str]:
    return {"X-Command-Id": str(command_id or uuid.uuid4())}


async def _ringing_call(s: AsyncSession) -> uuid.UUID:
    """Prime the shared mock provider with an incoming call, then mirror it as a
    ``calls`` row so the control endpoints can resolve it. Returns the row id."""
    from bbz_core.integrations_host.providers import active_telephony_provider

    provider = await active_telephony_provider()
    scid = provider.simulate_incoming(from_number="+49911500", to_line="1001")  # type: ignore[attr-defined]

    call = Call(
        bbz_call_id=f"CALL-{uuid.uuid4().hex[:8]}",
        provider="telephony_mock",
        source_call_id=scid,
        direction="inbound",
        state="ringing",
    )
    s.add(call)
    await s.flush()
    call_id = call.id
    await s.commit()
    return call_id


async def _audit_count(s: AsyncSession) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "CALL_CONTROL_ACTION")
        )
    ).scalar_one()


async def test_answer_translates_to_the_provider_and_is_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _ALL)
    await _login(client, "op")
    call_id = await _ringing_call(s)

    r = await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "answer" and body["accepted"] is True
    assert await _audit_count(s) == 1


async def test_duplicate_answer_command_does_not_hit_the_provider_twice(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _ALL)
    await _login(client, "op2")
    call_id = await _ringing_call(s)

    from bbz_core.integrations_host.providers import active_telephony_provider

    provider = await active_telephony_provider()
    await provider.drain_events()  # type: ignore[attr-defined]  # clear the priming events

    cid = uuid.uuid4()
    first = await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd(cid))
    second = await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd(cid))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()

    events = await provider.drain_events()  # type: ignore[attr-defined]
    assert [e.event_type.value for e in events].count("CALL_ANSWERED") == 1
    assert await _audit_count(s) == 1


async def test_transfer_requires_a_destination(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _ALL)
    await _login(client, "op3")
    call_id = await _ringing_call(s)

    assert (
        await client.post(f"/api/v1/calls/{call_id}/transfer", json={}, headers=_cmd())
    ).status_code == 422
    assert (
        await client.post(
            f"/api/v1/calls/{call_id}/transfer", json={"destination": ""}, headers=_cmd()
        )
    ).status_code == 422

    ok = await client.post(
        f"/api/v1/calls/{call_id}/transfer", json={"destination": "3000"}, headers=_cmd()
    )
    assert ok.status_code == 200 and ok.json()["action"] == "transfer"


async def test_hold_then_resume(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _ALL)
    await _login(client, "op4")
    call_id = await _ringing_call(s)
    await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd())
    assert (await client.post(f"/api/v1/calls/{call_id}/hold", headers=_cmd())).status_code == 200
    assert (await client.post(f"/api/v1/calls/{call_id}/resume", headers=_cmd())).status_code == 200


async def test_dial_starts_an_outbound_call(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", _ALL)
    await _login(client, "op5")
    r = await client.post(
        "/api/v1/calls/dial",
        json={"line_id": "1001", "destination": "110"},
        headers=_cmd(),
    )
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert await _audit_count(s) == 1


async def test_control_requires_the_matching_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "weak", ["calls.view", "calls.hangup"])  # no calls.answer
    await _login(client, "weak")
    call_id = await _ringing_call(s)
    assert (await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd())).status_code == 403
    assert (await client.post(f"/api/v1/calls/{call_id}/hangup", headers=_cmd())).status_code == 200


async def test_unknown_call_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op6", _ALL)
    await _login(client, "op6")
    r = await client.post(f"/api/v1/calls/{uuid.uuid4()}/answer", headers=_cmd())
    assert r.status_code == 404


async def test_call_without_a_provider_id_is_409(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op7", _ALL)
    await _login(client, "op7")
    call = Call(
        bbz_call_id=f"CALL-{uuid.uuid4().hex[:8]}",
        provider="telephony_mock",
        source_call_id=None,
        direction="inbound",
        state="offered",
    )
    s.add(call)
    await s.flush()
    call_id = call.id
    await s.commit()
    r = await client.post(f"/api/v1/calls/{call_id}/answer", headers=_cmd())
    assert r.status_code == 409
