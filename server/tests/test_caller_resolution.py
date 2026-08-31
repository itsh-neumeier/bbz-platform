"""Caller resolution on an inbound call (E11-08) — integration via the ingest path.

Number-normalization and match-case units live in
``test_phone_number_normalization.py`` / ``test_contact_matching.py``; this
drives a real mock call through ``POST /api/v1/telephony/events``.
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

from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority
from bbz_core.infra.models.telephony import Call


def _ev(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "Mock",
        "event_type": "CALL_RINGING",
        "source_call_id": "call-88",
        "calling_number": "+49911500123",
        "called_number": "110",
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
    os.environ["BBZ_JWT_SECRET"] = "caller-resolution-secret-at-least-32-byte!"
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


async def _contact(
    s: AsyncSession, name: str, e164: str, *, priority: str | None = None
) -> uuid.UUID:
    c = Contact(name=name)
    s.add(c)
    await s.flush()
    s.add(ContactNumber(contact_id=c.id, e164=e164, is_primary=True))
    if priority is not None:
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
    await _make_gateway(s)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "gw", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    yield client, s


async def _post(client: httpx.AsyncClient, **kw: Any) -> httpx.Response:
    return await client.post("/api/v1/telephony/events", json=_ev(**kw))


async def _call(s: AsyncSession) -> Call:
    await s.rollback()
    return (await s.execute(select(Call))).scalars().one()


async def test_a_known_caller_is_resolved_to_contact_and_priority(env: tuple) -> None:
    client, s = env
    cid = await _contact(s, "EVU Leitstelle", "+49911500123", priority="high")

    assert (await _post(client, calling_number="0911 500 123")).status_code == 200

    call = await _call(s)
    assert call.caller_contact_id == cid
    assert call.caller_priority == "high"


async def test_an_unknown_caller_leaves_the_resolution_empty(env: tuple) -> None:
    client, s = env
    await _contact(s, "Somebody", "+49911500123")
    assert (await _post(client, calling_number="+49301119999")).status_code == 200

    call = await _call(s)
    assert call.caller_contact_id is None
    assert call.caller_priority is None


async def test_a_contact_without_a_priority_resolves_with_a_null_priority(env: tuple) -> None:
    client, s = env
    cid = await _contact(s, "Netz AG", "+49911500123")
    assert (await _post(client, calling_number="+49911500123")).status_code == 200

    call = await _call(s)
    assert call.caller_contact_id == cid and call.caller_priority is None


async def test_an_extension_only_caller_is_not_resolved(env: tuple) -> None:
    client, s = env
    await _contact(s, "Whoever", "+49911500123", priority="low")
    assert (await _post(client, calling_number="42")).status_code == 200

    call = await _call(s)
    assert call.caller_contact_id is None


async def test_a_contact_added_mid_call_is_picked_up_on_a_later_event(env: tuple) -> None:
    client, s = env
    # first event: nobody in the book yet
    assert (
        await _post(client, event_type="CALL_RINGING", calling_number="+49911777888")
    ).status_code == 200
    assert (await _call(s)).caller_contact_id is None

    cid = await _contact(s, "Late Entry", "+49911777888", priority="medium")

    # a later event on the same call re-attempts the resolution
    assert (
        await _post(client, event_type="CALL_ANSWERED", calling_number="+49911777888")
    ).status_code == 200
    call = await _call(s)
    assert call.caller_contact_id == cid and call.caller_priority == "medium"


async def test_outbound_calls_are_not_caller_resolved(env: tuple) -> None:
    client, s = env
    await _contact(s, "Dialled Party", "+49911500123", priority="high")
    # provider marks an outbound call explicitly in metadata
    r = await _post(
        client,
        event_type="CALL_RINGING",
        calling_number="+49911500123",
        metadata={"direction": "outbound"},
    )
    assert r.status_code == 200
    call = await _call(s)
    assert call.direction == "outbound"
    assert call.caller_contact_id is None


async def test_resolution_does_not_emit_an_audit_or_domain_event(env: tuple) -> None:
    from bbz_core.infra.models.audit import AuditEvent
    from bbz_core.infra.models.domain_events import DomainEvent

    client, s = env
    await _contact(s, "EVU", "+49911500123", priority="high")
    await _post(client, calling_number="+49911500123")

    await s.rollback()
    actions = {
        r.action
        for r in (
            await s.execute(select(AuditEvent).where(AuditEvent.target_type == "call"))
        ).scalars()
    }
    assert "CALLER_RESOLVED" not in actions  # no such action — resolution is silent
    types = {r.event_type for r in (await s.execute(select(DomainEvent))).scalars()}
    assert types <= {"CALL_RINGING"}
