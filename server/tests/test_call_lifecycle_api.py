"""Provider events → call aggregate: state, domain events, audit (E11-04).

Drives the real ``POST /api/v1/telephony/events`` path so the dispatch hook
registered by ``create_app`` runs the ``CallLifecycleService``.
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

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.telephony import Call, CallParticipant


def _ev(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "Mock",
        "event_type": "CALL_RINGING",
        "source_call_id": "call-42",
        "calling_number": "+49911500",
        "called_number": "110",
        "display_name": "EVU Nord",
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
    os.environ["BBZ_JWT_SECRET"] = "call-lifecycle-secret-at-least-32-bytes-ok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_gateway(s: AsyncSession) -> None:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name="Gateway")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="gw")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key="r-gw", name="R")
    s.add(role)
    await s.flush()
    p = Permission(key="calls.ingest_provider_events", area="calls")
    s.add(p)
    await s.flush()
    s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_gateway(s)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "gw", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    yield client, s


async def _post(client: httpx.AsyncClient, **kw: Any) -> httpx.Response:
    return await client.post("/api/v1/telephony/events", json=_ev(**kw))


async def _one_call(s: AsyncSession) -> Call:
    await s.rollback()
    return (await s.execute(select(Call))).scalars().one()


async def test_first_event_creates_the_call_with_a_bbz_id(env: tuple) -> None:
    client, s = env
    assert (await _post(client, event_type="CALL_RINGING")).status_code == 200

    call = await _one_call(s)
    assert call.bbz_call_id.startswith("CALL-")
    assert call.source_call_id == "call-42"
    assert call.state == "ringing"
    assert call.direction == "inbound"
    assert call.provider == "telephony_mock"


async def test_lifecycle_transitions_and_domain_events(env: tuple) -> None:
    client, s = env
    for et in ("CALL_RINGING", "CALL_ANSWERED", "CALL_DISCONNECTED"):
        assert (await _post(client, event_type=et)).status_code == 200

    call = await _one_call(s)
    assert call.state == "disconnected"
    assert call.started_at is not None and call.ended_at is not None

    types = [
        r.event_type
        for r in (
            await s.execute(
                select(DomainEvent)
                .where(DomainEvent.aggregate_id == str(call.id))
                .order_by(DomainEvent.event_seq.asc())
            )
        ).scalars()
    ]
    assert types == ["CALL_RINGING", "CALL_ANSWERED", "CALL_ENDED"]

    audited = {
        r.action
        for r in (
            await s.execute(select(AuditEvent).where(AuditEvent.target_type == "call"))
        ).scalars()
    }
    assert audited == {"CALL_RINGING", "CALL_ANSWERED", "CALL_ENDED"}


async def test_reconnect_replay_does_not_double_process(env: tuple) -> None:
    client, s = env
    a = await _post(client, event_type="CALL_ANSWERED", telephony_event_id="t-a")
    b = await _post(client, event_type="CALL_ANSWERED", telephony_event_id="t-b")  # replay
    assert a.json()["outcome"] == "new" and b.json()["outcome"] == "duplicate"

    call = await _one_call(s)
    ringing_or_answered = [
        r.event_type
        for r in (
            await s.execute(select(DomainEvent).where(DomainEvent.aggregate_id == str(call.id)))
        ).scalars()
    ]
    assert ringing_or_answered.count("CALL_ANSWERED") == 1


async def test_participants_are_recorded_once(env: tuple) -> None:
    client, s = env
    await _post(client, event_type="CALL_RINGING")
    await _post(client, event_type="CALL_ANSWERED")  # same numbers again

    call = await _one_call(s)
    parts = (
        (await s.execute(select(CallParticipant).where(CallParticipant.call_id == call.id)))
        .scalars()
        .all()
    )
    by_role = {p.role: p.number for p in parts}
    assert by_role == {"caller": "+49911500", "callee": "110"}


async def test_line_and_cti_events_do_not_create_a_call(env: tuple) -> None:
    client, s = env
    r = await client.post(
        "/api/v1/telephony/events",
        json=_ev(event_type="CTI_PROVIDER_OUT_OF_SERVICE", source_call_id=None),
    )
    assert r.status_code == 200
    await s.rollback()
    assert (await s.execute(select(Call))).scalars().all() == []
