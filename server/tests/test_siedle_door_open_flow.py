"""Siedle door-open flow (roadmap E17-05, ADR-0025): "Öffnen" runs
answer? -> await media -> send DTMF once -> post-delay -> auto-hangup -> audited
result, transactionally and idempotently. The DTMF code is resolved transiently
and appears in no payload, audit row, or response (MASTER_PROMPT §30).

Backend compose over E17-01/02/03 + E11-05. The real JTAPI/SIP transport is
E12-05 / E13-06 (blocked); this runs against ``telephony_mock``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.door_open_commands import DoorOpenCommand
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.repositories.door_action_profiles import DoorActionProfileService
from bbz_core.integrations_host.providers import active_telephony_provider, reset_provider_cache

_CODE = "1234#"
_FROM = "+49110"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "door-open-test-secret-at-least-32-bytes-x!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_DOOR_DTMF_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    os.environ.pop("BBZ_DOOR_DTMF_ENCRYPTION_KEY", None)


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


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def _door(s: AsyncSession, *, delay_ms: int = 20, timeout: int | None = 5) -> uuid.UUID:
    """A door_station endpoint wired to a real encrypted DTMF profile."""
    profile = await DoorActionProfileService(s).create(
        name=f"Haupttor {uuid.uuid4().hex[:6]}",
        dtmf_code=_CODE,
        post_dtmf_delay_ms=delay_ms,
        auto_hangup=True,
        actor_id=None,
    )
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Klingel Haupteingang",
            type="door_station",
            dtmf_profile_id=profile.id,
            popup_text="Klingeln: Haupteingang",
            door_open_timeout_seconds=timeout,
        )
        s.add(ep)
        await s.flush()
        return ep.id


async def _ringing_call(to_line: str = "1001") -> str:
    provider = await active_telephony_provider()
    return provider.simulate_incoming(from_number=_FROM, to_line=to_line)  # type: ignore[attr-defined]


async def _rows(s: AsyncSession) -> list[DoorOpenCommand]:
    await s.rollback()
    return list((await s.execute(select(DoorOpenCommand))).scalars().all())


async def _audits(s: AsyncSession, action: str) -> list[AuditEvent]:
    await s.rollback()
    return list(
        (await s.execute(select(AuditEvent).where(AuditEvent.action == action))).scalars().all()
    )


async def test_a_ring_is_opened_answer_dtmf_once_then_hangup(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s)
    call_id = await _ringing_call()
    provider = await active_telephony_provider()

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=_cmd()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "opened" and body["opened"] is True

    # the DTMF sequence was emitted exactly once, the call was hung up
    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
    assert await provider.get_active_calls() == []

    await s.rollback()
    row = (await s.execute(select(DoorOpenCommand))).scalars().one()
    state, outcome = row.state, row.outcome
    dtmf_sent, completed = row.dtmf_sent_at, row.completed_at
    assert state == "done" and outcome == "opened"
    assert dtmf_sent is not None and completed is not None

    # audited both sides, profile id only, never the code
    await s.rollback()
    afters = {
        a.action: dict(a.after or {})
        for a in (await s.execute(select(AuditEvent))).scalars().all()
        if a.action.startswith("DOOR_OPEN_")
    }
    assert afters["DOOR_OPEN_REQUESTED"]["door_action_profile_id"] is not None
    assert afters["DOOR_OPEN_RESULT"]["outcome"] == "opened"
    for after in afters.values():
        assert "1234" not in str(after) and _CODE not in str(after)


async def test_same_command_id_replays_and_never_opens_twice(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s)
    call_id = await _ringing_call()
    provider = await active_telephony_provider()

    await _login(client, "op")
    headers = _cmd()
    first = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=headers
    )
    second = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=headers
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()

    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
    assert len(await _rows(s)) == 1
    assert len(await _audits(s, "DOOR_OPEN_RESULT")) == 1


async def test_a_call_that_is_already_gone_yields_caller_gone_and_no_dtmf(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s)
    provider = await active_telephony_provider()

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open",
        json={"call_id": "mock-does-not-exist"},
        headers=_cmd(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "caller_gone" and r.json()["opened"] is False
    assert provider._dtmf_sends == []  # type: ignore[attr-defined]
    assert (await _rows(s))[0].state == "failed"


async def test_a_call_that_never_reaches_media_times_out_without_dtmf(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s, timeout=1)
    provider = await active_telephony_provider()
    call_id = provider.simulate_incoming(from_number=_FROM, to_line="1001")  # type: ignore[attr-defined]
    await provider.hold(call_id=call_id, command_id="wedge")  # parked in HELD, never CONNECTED

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=_cmd()
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "media_timeout" and r.json()["opened"] is False
    assert provider._dtmf_sends == []  # type: ignore[attr-defined]
    assert (await _rows(s))[0].state == "timed_out"


async def test_door_open_requires_the_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "weak", ["door.view"])
    endpoint_id = await _door(s)
    call_id = await _ringing_call()

    await _login(client, "weak")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=_cmd()
    )
    assert r.status_code == 403
    assert (await s.execute(select(func.count()).select_from(DoorOpenCommand))).scalar_one() == 0


async def test_a_door_station_without_a_profile_yields_no_profile(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(name="Klingel ohne Profil", type="door_station")
        s.add(ep)
        await s.flush()
        endpoint_id = ep.id
    call_id = await _ringing_call()
    provider = await active_telephony_provider()

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=_cmd()
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "no_profile" and r.json()["opened"] is False
    assert provider._dtmf_sends == []  # type: ignore[attr-defined]
    row = (await _rows(s))[0]
    assert row.state == "failed" and row.outcome == "no_profile"
    # the attempt is still fully audited
    assert len(await _audits(s, "DOOR_OPEN_REQUESTED")) == 1
    assert len(await _audits(s, "DOOR_OPEN_RESULT")) == 1


async def test_a_non_door_endpoint_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(name="BMA Nord", type="bma")
        s.add(ep)
        await s.flush()
        bma_id = ep.id

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{bma_id}/open", json={"call_id": "mock-1"}, headers=_cmd()
    )
    assert r.status_code == 404


async def test_the_dtmf_code_is_nowhere_in_persisted_state(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s)
    call_id = await _ringing_call()

    await _login(client, "op")
    r = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=_cmd()
    )
    assert _CODE not in r.text and "1234" not in r.text

    await s.rollback()
    for row in await _rows(s):
        blob = f"{row.state}{row.outcome}{row.detail}{row.call_id}"
        assert "1234" not in blob
    for a in (await s.execute(select(AuditEvent))).scalars().all():
        assert "1234" not in str(a.before) and "1234" not in str(a.after)


async def test_a_purged_idempotency_row_still_never_opens_twice(env: tuple) -> None:
    """Failover window: the durable command row is gone but the door_open_commands
    state machine row survives → the retry replays it, no second DTMF (ADR-0025)."""
    from sqlalchemy import delete

    from bbz_core.infra.models.commands import Command
    from bbz_core.infra.repositories.door_open import DoorOpenService

    _, s = env
    actor = await _make_user(s, "op", ["door.open"])
    endpoint_id = await _door(s)
    call_id = await _ringing_call()
    provider = await active_telephony_provider()
    command_id = uuid.uuid4()

    first = await DoorOpenService(s).open(
        endpoint_id=endpoint_id, call_id=call_id, command_id=command_id, actor_id=actor
    )
    assert first.outcome == "opened"

    # simulate the crash-before-complete + housekeeping purge
    await s.rollback()
    async with s.begin():
        await s.execute(delete(Command).where(Command.command_id == command_id))

    second = await DoorOpenService(s).open(
        endpoint_id=endpoint_id, call_id=call_id, command_id=command_id, actor_id=actor
    )
    assert second == first
    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
    assert len(await _rows(s)) == 1
