"""PUT/GET /calls/{id}/documentation — mandatory categorization (E11-09)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.telephony import Call


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "call-doc-secret-at-least-32-bytes-thanks-!!"
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
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, uuid.UUID]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", ["calls.document", "calls.view"])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "op", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200

    call = Call(
        bbz_call_id=f"CALL-{uuid.uuid4().hex[:8]}",
        provider="telephony_mock",
        source_call_id=f"s-{uuid.uuid4().hex[:6]}",
        direction="inbound",
        state="connected",
    )
    s.add(call)
    await s.flush()
    cid = call.id
    await s.commit()
    yield client, s, cid


async def _count(s: AsyncSession, model: type, value: str, col: str) -> int:
    await s.rollback()
    return (
        await s.execute(select(func.count()).select_from(model).where(getattr(model, col) == value))
    ).scalar_one()


async def test_free_text_only_does_not_document_the_call(env: tuple) -> None:
    client, s, cid = env
    r = await client.put(
        f"/api/v1/calls/{cid}/documentation", json={"free_text": "Notiz während des Gesprächs"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category"] is None and body["mandatory_done"] is False
    assert body["free_text"] == "Notiz während des Gesprächs"
    assert await _count(s, DomainEvent, "CALL_DOCUMENTED", "event_type") == 0


async def test_setting_a_category_documents_and_audits(env: tuple) -> None:
    client, s, cid = env
    r = await client.put(
        f"/api/v1/calls/{cid}/documentation",
        json={"category": "technical_fault", "free_text": "Weiche klemmt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "technical_fault" and body["mandatory_done"] is True
    assert body["documented_by"] is not None and body["documented_at"] is not None
    assert await _count(s, DomainEvent, "CALL_DOCUMENTED", "event_type") == 1
    assert await _count(s, AuditEvent, "CALL_DOCUMENTED", "action") == 1


async def test_an_unknown_category_is_422(env: tuple) -> None:
    client, _s, cid = env
    r = await client.put(f"/api/v1/calls/{cid}/documentation", json={"category": "smalltalk"})
    assert r.status_code == 422


async def test_re_saving_overwrites_last_state_wins(env: tuple) -> None:
    client, s, cid = env
    await client.put(
        f"/api/v1/calls/{cid}/documentation", json={"category": "other", "free_text": "erst"}
    )
    r2 = await client.put(
        f"/api/v1/calls/{cid}/documentation",
        json={"category": "information_request", "free_text": "korrigiert"},
    )
    assert r2.status_code == 200
    got = (await client.get(f"/api/v1/calls/{cid}/documentation")).json()
    assert got["category"] == "information_request" and got["free_text"] == "korrigiert"

    # one CallDocumentation row, two CALL_DOCUMENTED events + audits (both saves)
    await s.rollback()
    from bbz_core.infra.models.telephony import CallDocumentation

    rows = (
        (await s.execute(select(CallDocumentation).where(CallDocumentation.call_id == cid)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert await _count(s, AuditEvent, "CALL_DOCUMENTED", "action") == 2


async def test_clearing_the_category_drops_mandatory_done(env: tuple) -> None:
    client, _s, cid = env
    await client.put(f"/api/v1/calls/{cid}/documentation", json={"category": "other"})
    r = await client.put(
        f"/api/v1/calls/{cid}/documentation", json={"category": None, "free_text": "nur Text"}
    )
    assert r.status_code == 200 and r.json()["mandatory_done"] is False


async def test_get_before_any_save_returns_empty(env: tuple) -> None:
    client, _s, cid = env
    got = (await client.get(f"/api/v1/calls/{cid}/documentation")).json()
    assert got == {
        "call_id": str(cid),
        "category": None,
        "free_text": None,
        "documented_by": None,
        "documented_at": None,
        "mandatory_done": False,
    }


async def test_documentation_requires_the_calls_document_permission(env: tuple) -> None:
    client, s, cid = env
    await _make_user(s, "weak", ["calls.view"])
    r = await client.post(
        "/api/v1/auth/login", json={"username": "weak", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    assert (
        await client.put(f"/api/v1/calls/{cid}/documentation", json={"category": "other"})
    ).status_code == 403
    # read is allowed with calls.view
    assert (await client.get(f"/api/v1/calls/{cid}/documentation")).status_code == 200


async def test_unknown_call_is_404(env: tuple) -> None:
    client, _s, _cid = env
    assert (
        await client.put(f"/api/v1/calls/{uuid.uuid4()}/documentation", json={"category": "other"})
    ).status_code == 404
