"""GET /api/v1/audit — filters, pagination, permission (E04-04)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "auditq-test-secret-at-least-32-bytes-okay!!"
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
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
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


async def _seed(s: AsyncSession, n: int, *, action: str, target_id: str, corr: str) -> None:
    for _ in range(n):
        s.add(
            AuditEvent(
                node_id="BBZ-TEST",
                action=action,
                target_type="event",
                target_id=target_id,
                correlation_id=corr,
            )
        )
    await s.commit()


async def test_filters_action_target_and_correlation(env: tuple) -> None:
    client, s = env
    await _make_user(s, "auditor", ["system.audit.view"])
    tid = str(uuid.uuid4())
    await _seed(s, 2, action="EVENT_ARCHIVED", target_id=tid, corr="c-1")
    await _seed(s, 3, action="EVENT_REACTIVATED", target_id=str(uuid.uuid4()), corr="c-2")
    await _login(client, "auditor")

    by_action = (await client.get("/api/v1/audit?action=EVENT_ARCHIVED")).json()
    assert {r["action"] for r in by_action["items"]} == {"EVENT_ARCHIVED"}

    by_target = (await client.get(f"/api/v1/audit?target_id={tid}")).json()
    assert len(by_target["items"]) == 2

    by_corr = (await client.get("/api/v1/audit?correlation_id=c-2")).json()
    assert len(by_corr["items"]) == 3


async def test_pagination_is_stable_across_an_append(env: tuple) -> None:
    client, s = env
    await _make_user(s, "auditor2", ["system.audit.view"])
    tid = str(uuid.uuid4())
    await _seed(s, 3, action="EVENT_ARCHIVED", target_id=tid, corr="p")
    await _login(client, "auditor2")

    page1 = (await client.get(f"/api/v1/audit?target_id={tid}&limit=2")).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]

    await _seed(s, 1, action="EVENT_ARCHIVED", target_id=tid, corr="p")  # concurrent append

    page2 = (
        await client.get(f"/api/v1/audit?target_id={tid}&limit=2&cursor={page1['next_cursor']}")
    ).json()
    assert len(page2["items"]) == 1
    ids = {r["id"] for r in page1["items"]} | {r["id"] for r in page2["items"]}
    assert len(ids) == 3  # the original three, none repeated or dropped


async def test_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "plain", [])
    await _login(client, "plain")
    assert (await client.get("/api/v1/audit")).status_code == 403


async def test_no_write_route_on_audit() -> None:
    from fastapi.routing import APIRoute

    from bbz_core.app import create_app

    writes = [
        f"{m} {r.path}"
        for r in create_app().routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/v1/audit")
        for m in r.methods & {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert writes == []
