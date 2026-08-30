"""GET /lines + LINE_IN/OUT_OF_SERVICE from normalized events (E11-07)."""

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

from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.telephony import Line


def _line_event(external_id: str, event_type: str, **kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "MockLine",
        "event_type": event_type,
        "line_id": external_id,
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
    os.environ["BBZ_JWT_SECRET"] = "line-status-secret-at-least-32-bytes-okayy!"
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
    await _make_user(s, "gw", ["calls.ingest_provider_events", "calls.view"])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "gw", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    yield client, s


async def _ingest(client: httpx.AsyncClient, ev: dict[str, Any]) -> httpx.Response:
    return await client.post("/api/v1/telephony/events", json=ev)


async def test_line_outage_shows_up_in_the_api_and_the_stream(env: tuple) -> None:
    client, s = env

    assert (await _ingest(client, _line_event("SEP01", "LINE_IN_SERVICE"))).status_code == 200
    lines = (await client.get("/api/v1/lines")).json()["lines"]
    assert [(x["external_id"], x["state"]) for x in lines] == [("SEP01", "in_service")]

    assert (await _ingest(client, _line_event("SEP01", "LINE_OUT_OF_SERVICE"))).status_code == 200
    lines = (await client.get("/api/v1/lines")).json()["lines"]
    assert lines[0]["state"] == "out_of_service"

    # each real change appended a LINE_* domain event (→ event stream)
    await s.rollback()
    types = [
        r.event_type
        for r in (
            await s.execute(
                select(DomainEvent)
                .where(DomainEvent.aggregate_type == "line")
                .order_by(DomainEvent.event_seq.asc())
            )
        ).scalars()
    ]
    assert types == ["LINE_IN_SERVICE", "LINE_OUT_OF_SERVICE"]


async def test_repeated_same_state_does_not_emit_a_second_event(env: tuple) -> None:
    client, s = env
    await _ingest(client, _line_event("SEP02", "LINE_OUT_OF_SERVICE"))
    await _ingest(client, _line_event("SEP02", "LINE_OUT_OF_SERVICE"))  # same state again

    await s.rollback()
    count = len(
        (await s.execute(select(DomainEvent).where(DomainEvent.aggregate_type == "line")))
        .scalars()
        .all()
    )
    assert count == 1


async def test_lines_endpoint_requires_calls_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "noview", ["calls.answer"])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "noview", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/lines")).status_code == 403


async def test_provider_filter(env: tuple) -> None:
    client, s = env
    s.add(Line(provider="cucm", external_id="X", state="in_service"))
    await s.commit()
    await _ingest(client, _line_event("SEP03", "LINE_IN_SERVICE"))

    all_lines = (await client.get("/api/v1/lines")).json()["lines"]
    assert {x["provider"] for x in all_lines} == {"cucm", "telephony_mock"}
    only_mock = (await client.get("/api/v1/lines?provider=telephony_mock")).json()["lines"]
    assert [x["external_id"] for x in only_mock] == ["SEP03"]
