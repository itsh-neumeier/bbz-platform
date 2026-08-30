"""One command -> one correlation_id across event / audit / outbox (E04-09)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox

_PERMS = ["events.create", "events.assign", "events.takeover"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "corr-test-secret-at-least-32-bytes-long-ok!!"
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


def _fresh(client: httpx.AsyncClient) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def _event_corr(s: AsyncSession) -> set[str | None]:
    rows = (
        (
            await s.execute(
                select(DomainEvent.correlation_id).where(
                    DomainEvent.event_type == "EVENT_TAKEN_OVER"
                )
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _audit_corr(s: AsyncSession) -> set[str | None]:
    rows = (
        (
            await s.execute(
                select(AuditEvent.correlation_id).where(AuditEvent.action == "EVENT_TAKEN_OVER")
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _outbox_corr(s: AsyncSession) -> set[str | None]:
    rows = (await s.execute(select(ExternalActionOutbox.correlation_id))).scalars().all()
    return set(rows)


async def _takeover_setup(client: httpx.AsyncClient, s: AsyncSession) -> str:
    await _make_user(s, "disp", _PERMS)
    owner = await _make_user(s, "owner", [])
    await _make_user(s, "taker", ["events.takeover"])
    await _login(client, "disp")
    eid = (
        await client.post(
            "/api/v1/events",
            json={"title": "Oberleitungsschaden", "priority": "critical"},
            headers={"X-Command-Id": str(uuid.uuid4())},
        )
    ).json()["id"]
    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(owner)},
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "1"},
    )
    assert r.status_code == 200, r.text
    return eid


async def test_supplied_correlation_id_reaches_all_sinks(env: tuple) -> None:
    client, s = env
    eid = await _takeover_setup(client, s)
    cid = f"corr-{uuid.uuid4()}"

    taker = _fresh(client)
    await _login(taker, "taker")
    r = await taker.post(
        f"/api/v1/events/{eid}/takeover",
        headers={
            "X-Command-Id": str(uuid.uuid4()),
            "X-Expected-Version": "2",
            "X-Correlation-Id": cid,
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["x-correlation-id"] == cid

    assert await _event_corr(s) == {cid}
    assert await _audit_corr(s) == {cid}
    assert await _outbox_corr(s) == {cid}


async def test_missing_header_server_generates_and_echoes_consistently(env: tuple) -> None:
    client, s = env
    eid = await _takeover_setup(client, s)

    taker = _fresh(client)
    await _login(taker, "taker")
    r = await taker.post(
        f"/api/v1/events/{eid}/takeover",
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "2"},
    )
    assert r.status_code == 200
    generated = r.headers["x-correlation-id"]
    assert uuid.UUID(generated)  # a real uuid

    assert await _event_corr(s) == {generated}
    assert await _audit_corr(s) == {generated}
    assert await _outbox_corr(s) == {generated}
