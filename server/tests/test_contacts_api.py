"""Phone-book API: CRUD, search, permissions, idempotency (E14-02)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.contacts import Contact

_ALL = [
    "contacts.view",
    "contacts.create",
    "contacts.edit",
    "contacts.delete",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "contacts-api-secret-at-least-32-bytes-ok!!"
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


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


@pytest.fixture
async def api(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", _ALL)
    await _make_user(s, "viewer", ["contacts.view"])
    await _login(client, "op")
    yield client, s


async def _create(client: httpx.AsyncClient, **over: object) -> httpx.Response:
    body: dict[str, object] = {"name": "EVU Leitstelle", "org": "Netz AG"}
    body.update(over)
    return await client.post("/api/v1/contacts", json=body, headers=_cmd())


async def test_create_returns_201_with_location_and_numbers(api: tuple) -> None:
    client, _ = api
    r = await _create(
        client,
        name="Siedle Service",
        numbers=[
            {"e164": "+49711111", "label": "Zentrale", "is_primary": True},
            {"e164": "+49711222"},
        ],
    )
    assert r.status_code == 201
    body = r.json()
    assert r.headers["location"] == f"/api/v1/contacts/{body['id']}"
    assert body["name"] == "Siedle Service"
    assert body["priority"] is None
    assert {n["e164"] for n in body["numbers"]} == {"+49711111", "+49711222"}
    assert [n["e164"] for n in body["numbers"] if n["is_primary"]] == ["+49711111"]


async def test_create_requires_the_create_permission(api: tuple) -> None:
    client, _ = api
    await _login(client, "viewer")
    assert (await _create(client)).status_code == 403


async def test_create_is_idempotent_on_command_id_replay(api: tuple) -> None:
    client, s = api
    headers = _cmd()
    body = {"name": "Doppelt", "org": "X"}
    r1 = await client.post("/api/v1/contacts", json=body, headers=headers)
    r2 = await client.post("/api/v1/contacts", json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    n = (
        await s.execute(select(func.count()).select_from(Contact).where(Contact.name == "Doppelt"))
    ).scalar_one()
    assert n == 1


async def test_reused_command_id_with_a_different_body_is_409(api: tuple) -> None:
    client, _ = api
    headers = _cmd()
    assert (
        await client.post("/api/v1/contacts", json={"name": "A"}, headers=headers)
    ).status_code == 201
    r = await client.post("/api/v1/contacts", json={"name": "B"}, headers=headers)
    assert r.status_code == 409


async def test_invalid_e164_is_rejected_before_the_db(api: tuple) -> None:
    client, _ = api
    r = await _create(client, numbers=[{"e164": "0711 55 66"}])
    assert r.status_code == 422


async def test_get_unknown_contact_is_404(api: tuple) -> None:
    client, _ = api
    assert (await client.get(f"/api/v1/contacts/{uuid.uuid4()}")).status_code == 404


async def test_patch_updates_fields_and_audits(api: tuple) -> None:
    client, s = api
    cid = (await _create(client, name="Alt", org="Alt AG")).json()["id"]

    r = await client.patch(
        f"/api/v1/contacts/{cid}", json={"name": "Neu", "quick_dial": True, "org": None}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Neu" and body["quick_dial"] is True and body["org"] is None

    row = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "CONTACT_UPDATED"))
    ).scalar_one()
    assert row.target_id == cid
    assert row.before["name"] == "Alt"
    assert row.after["name"] == "Neu"


async def test_patch_requires_the_edit_permission(api: tuple) -> None:
    client, _ = api
    cid = (await _create(client)).json()["id"]
    await _login(client, "viewer")
    assert (await client.patch(f"/api/v1/contacts/{cid}", json={"name": "X"})).status_code == 403


async def test_delete_is_soft_and_audited(api: tuple) -> None:
    client, s = api
    cid = (await _create(client, name="Weg")).json()["id"]

    assert (await client.delete(f"/api/v1/contacts/{cid}")).status_code == 204
    assert (await client.get(f"/api/v1/contacts/{cid}")).status_code == 404
    assert (await client.get("/api/v1/contacts", params={"q": "Weg"})).json()["items"] == []

    await s.rollback()
    deleted_at = (
        await s.execute(select(Contact.deleted_at).where(Contact.id == uuid.UUID(cid)))
    ).scalar_one()
    assert deleted_at is not None

    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "CONTACT_DELETED")
        )
    ).scalar_one() == 1

    # deleting again is a 404 (already gone)
    assert (await client.delete(f"/api/v1/contacts/{cid}")).status_code == 404


async def test_delete_requires_the_delete_permission(api: tuple) -> None:
    client, _ = api
    cid = (await _create(client)).json()["id"]
    await _login(client, "viewer")
    assert (await client.delete(f"/api/v1/contacts/{cid}")).status_code == 403


async def test_search_matches_name_org_and_number_case_insensitively(api: tuple) -> None:
    client, _ = api
    a = (await _create(client, name="Alice Ackermann", org="Alpha")).json()["id"]
    b = (await _create(client, name="Bob Bauer", org="Beta")).json()["id"]
    await _create(client, name="Carol", org="Gamma", numbers=[{"e164": "+49999123"}])

    by_name = (await client.get("/api/v1/contacts", params={"q": "ACKER"})).json()["items"]
    assert [c["id"] for c in by_name] == [a]

    by_org = (await client.get("/api/v1/contacts", params={"q": "beta"})).json()["items"]
    assert [c["id"] for c in by_org] == [b]

    by_num = (await client.get("/api/v1/contacts", params={"q": "999123"})).json()["items"]
    assert [c["name"] for c in by_num] == ["Carol"]


async def test_search_is_alphabetical_and_keyset_paginated(api: tuple) -> None:
    client, _ = api
    for name in ("Delta", "Bravo", "Alfa", "Charlie", "Echo"):
        await _create(client, name=name)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params = {"limit": "2"}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/contacts", params=params)).json()
        seen.extend(c["name"] for c in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["Alfa", "Bravo", "Charlie", "Delta", "Echo"]


async def test_search_requires_the_view_permission(api: tuple) -> None:
    client, s = api
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/contacts")).status_code == 403


async def test_a_malformed_cursor_is_422(api: tuple) -> None:
    client, _ = api
    assert (
        await client.get("/api/v1/contacts", params={"cursor": "###not-base64###"})
    ).status_code == 422


async def test_number_sub_resource_crud_and_primary_demotion(api: tuple) -> None:
    client, _ = api
    cid = (await _create(client, numbers=[{"e164": "+49711000", "is_primary": True}])).json()["id"]

    r = await client.post(
        f"/api/v1/contacts/{cid}/numbers",
        json={"e164": "+49711999", "label": "Mobil", "is_primary": True},
    )
    assert r.status_code == 201
    new_id = r.json()["id"]

    numbers = (await client.get(f"/api/v1/contacts/{cid}/numbers")).json()
    primary = [n["e164"] for n in numbers if n["is_primary"]]
    assert primary == ["+49711999"]  # the old primary was demoted

    assert (
        await client.patch(
            f"/api/v1/contacts/{cid}/numbers/{new_id}", json={"label": "Diensthandy"}
        )
    ).status_code == 200
    assert (await client.delete(f"/api/v1/contacts/{cid}/numbers/{new_id}")).status_code == 204
    left = (await client.get(f"/api/v1/contacts/{cid}/numbers")).json()
    assert [n["e164"] for n in left] == ["+49711000"]


async def test_duplicate_number_on_one_contact_is_409(api: tuple) -> None:
    client, _ = api
    cid = (await _create(client, numbers=[{"e164": "+49711000"}])).json()["id"]
    r = await client.post(f"/api/v1/contacts/{cid}/numbers", json={"e164": "+49711000"})
    assert r.status_code == 409


async def test_create_writes_exactly_one_contact_created_audit_row(api: tuple) -> None:
    client, s = api
    await _create(client, name="Auditiert")
    rows = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "CONTACT_CREATED")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].after["name"] == "Auditiert"
