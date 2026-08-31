"""GET /contacts?quick_dial=true — the speed-dial list (E14-06)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "quickdial-secret-at-least-32-bytes-thanks!"
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


@pytest.fixture
async def api(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(
        s, "op", ["contacts.view", "contacts.create", "contacts.edit", "contacts.delete"]
    )
    r = await client.post(
        "/api/v1/auth/login", json={"username": "op", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    yield client, s


async def _add(client: httpx.AsyncClient, name: str, *, quick_dial: bool = False) -> str:
    r = await client.post(
        "/api/v1/contacts",
        json={"name": name, "quick_dial": quick_dial},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _names(body: dict) -> list[str]:
    return [c["name"] for c in body["items"]]


async def test_list_contains_only_marked_contacts_alphabetically(api: tuple) -> None:
    client, _ = api
    await _add(client, "Delta", quick_dial=True)
    await _add(client, "Alfa", quick_dial=True)
    await _add(client, "Bravo", quick_dial=False)
    await _add(client, "Charlie", quick_dial=True)

    body = (await client.get("/api/v1/contacts", params={"quick_dial": "true"})).json()
    assert _names(body) == ["Alfa", "Charlie", "Delta"]


async def test_quick_dial_false_returns_the_complement(api: tuple) -> None:
    client, _ = api
    await _add(client, "Marked", quick_dial=True)
    await _add(client, "Plain", quick_dial=False)

    body = (await client.get("/api/v1/contacts", params={"quick_dial": "false"})).json()
    assert _names(body) == ["Plain"]


async def test_no_filter_still_returns_everything(api: tuple) -> None:
    client, _ = api
    await _add(client, "Marked", quick_dial=True)
    await _add(client, "Plain", quick_dial=False)

    assert set(_names((await client.get("/api/v1/contacts")).json())) == {"Marked", "Plain"}


async def test_toggling_the_flag_moves_the_contact_in_and_out_of_the_list(api: tuple) -> None:
    client, _ = api
    cid = await _add(client, "Wanderer", quick_dial=False)

    q = {"quick_dial": "true"}
    assert _names((await client.get("/api/v1/contacts", params=q)).json()) == []

    await client.patch(f"/api/v1/contacts/{cid}", json={"quick_dial": True})
    assert _names((await client.get("/api/v1/contacts", params=q)).json()) == ["Wanderer"]

    await client.patch(f"/api/v1/contacts/{cid}", json={"quick_dial": False})
    assert _names((await client.get("/api/v1/contacts", params=q)).json()) == []


async def test_a_soft_deleted_quick_dial_contact_drops_off_the_list(api: tuple) -> None:
    client, _ = api
    cid = await _add(client, "Gone", quick_dial=True)
    await client.delete(f"/api/v1/contacts/{cid}")
    body = (await client.get("/api/v1/contacts", params={"quick_dial": "true"})).json()
    assert _names(body) == []


async def test_the_quick_dial_list_is_keyset_paginated_and_stable(api: tuple) -> None:
    client, _ = api
    for name in ("Echo", "Alfa", "Delta", "Bravo", "Charlie"):
        await _add(client, name, quick_dial=True)
    await _add(client, "Zeta", quick_dial=False)  # noise

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params = {"quick_dial": "true", "limit": "2"}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get("/api/v1/contacts", params=params)).json()
        seen.extend(_names(body))
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert seen == ["Alfa", "Bravo", "Charlie", "Delta", "Echo"]
