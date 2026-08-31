"""PUT /contacts/{id}/priority — assignment, no-op, rights (E14-03)."""

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


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "contact-prio-secret-at-least-32-bytes-ok!!"
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


@pytest.fixture
async def api(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, str]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", ["contacts.view", "contacts.create", "contacts.assign_priority"])
    await _make_user(s, "weak", ["contacts.view", "contacts.create"])
    await _login(client, "op")
    r = await client.post(
        "/api/v1/contacts",
        json={"name": "EVU Leitstelle"},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 201
    yield client, s, r.json()["id"]


async def _events(s: AsyncSession, cid: str) -> list[str]:
    """Priority events only — POST /contacts also emits CONTACT_CREATED (E14-05)."""
    await s.rollback()
    return list(
        (
            await s.execute(
                select(DomainEvent.event_type)
                .where(
                    DomainEvent.aggregate_id == cid,
                    DomainEvent.event_type == "CONTACT_PRIORITY_CHANGED",
                )
                .order_by(DomainEvent.event_seq.asc())
            )
        ).scalars()
    )


async def _audit_rows(s: AsyncSession) -> list[dict]:
    await s.rollback()
    rows = (
        await s.execute(
            select(AuditEvent.before, AuditEvent.after, AuditEvent.event_seq_ref)
            .where(AuditEvent.action == "CONTACT_PRIORITY_CHANGED")
            .order_by(AuditEvent.occurred_at_utc.asc())
        )
    ).all()
    return [{"before": b, "after": a, "event_seq_ref": r} for b, a, r in rows]


async def test_first_assignment_emits_one_event_and_audit_with_null_from(api: tuple) -> None:
    client, s, cid = api
    r = await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "high"})
    assert r.status_code == 200
    assert r.json() == {"contact_id": cid, "priority": "high", "changed": True}

    assert await _events(s, cid) == ["CONTACT_PRIORITY_CHANGED"]
    rows = await _audit_rows(s)
    assert len(rows) == 1
    assert rows[0]["before"] == {"priority": None}
    assert rows[0]["after"] == {"priority": "high"}
    assert rows[0]["event_seq_ref"] is not None


async def test_changing_the_level_records_before_and_after(api: tuple) -> None:
    client, s, cid = api
    await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "low"})
    r = await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "high"})
    assert r.json()["changed"] is True

    assert await _events(s, cid) == ["CONTACT_PRIORITY_CHANGED", "CONTACT_PRIORITY_CHANGED"]
    rows = await _audit_rows(s)
    assert [(x["before"]["priority"], x["after"]["priority"]) for x in rows] == [
        (None, "low"),
        ("low", "high"),
    ]


async def test_assigning_the_same_level_is_a_no_op(api: tuple) -> None:
    client, s, cid = api
    await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "medium"})
    r = await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "medium"})
    assert r.status_code == 200
    assert r.json()["changed"] is False

    assert await _events(s, cid) == ["CONTACT_PRIORITY_CHANGED"]  # still just the first
    assert len(await _audit_rows(s)) == 1


async def test_invalid_priority_is_422(api: tuple) -> None:
    client, _, cid = api
    r = await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "urgent"})
    assert r.status_code == 422


async def test_priority_requires_the_assign_permission(api: tuple) -> None:
    client, _, cid = api
    await _login(client, "weak")
    r = await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "high"})
    assert r.status_code == 403


async def test_priority_on_an_unknown_contact_is_404(api: tuple) -> None:
    client, _, _cid = api
    r = await client.put(f"/api/v1/contacts/{uuid.uuid4()}/priority", json={"priority": "low"})
    assert r.status_code == 404


async def test_the_assigned_priority_shows_up_in_reads(api: tuple) -> None:
    client, _, cid = api
    await client.put(f"/api/v1/contacts/{cid}/priority", json={"priority": "high"})

    assert (await client.get(f"/api/v1/contacts/{cid}")).json()["priority"] == "high"
    hit = (await client.get("/api/v1/contacts", params={"q": "EVU"})).json()["items"][0]
    assert hit["priority"] == "high"
