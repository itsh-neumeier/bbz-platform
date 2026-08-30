"""ArchiveQueryRepository.detail — same detail depth active vs. archived (E20-01).

Archiving only ever *adds* rows (a status-history entry, an audit entry, a domain
event). The archive-detail aggregator therefore returns at least the same depth
for an archived event as it did while the event was active. Nothing is deleted.

The HTTP surface is E20-03 (`test_archive_detail_api.py`); here the aggregator
query is exercised directly against the DB.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.repositories.archive_queries import ArchiveDetail, ArchiveQueryRepository

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.postprocess",
    "events.archive",
    "events.reactivate",
    "events.view",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "archive-detail-secret-at-least-32-bytes-ok!!"
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
    yield client, s


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _opened_event_with_note(client: httpx.AsyncClient) -> uuid.UUID:
    r = await client.post(
        "/api/v1/events",
        json={"title": "Fahrgastnotruf B2", "priority": "high", "description": "Bahnsteig 2"},
        headers=_cmd(),
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        rr = await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        assert rr.status_code == 200, rr.text
    n = await client.post(
        f"/api/v1/events/{eid}/notes", json={"body": "Techniker vor Ort"}, headers=_cmd()
    )
    assert n.status_code == 201, n.text
    return uuid.UUID(eid)  # status "opened", version 4


def _depth(bundle: ArchiveDetail) -> dict[str, Any]:
    """The comparable shape — everything except the always-growing audit trail."""
    d = bundle.detail
    return {
        "status_history": [(h.from_status, h.to_status) for h in d.status_history],
        "notes": [(n.kind, n.body) for n in d.notes],
        "description": d.description,
        "domain_events": [e.event_type for e in bundle.domain_events],
        "workflows": bundle.workflows,
        "calls": bundle.calls,
    }


async def test_archive_detail_depth_is_identical_active_vs_archived(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _opened_event_with_note(client)

    await s.rollback()
    while_active = _depth(await _detail(s, eid))

    arch = await client.post(
        f"/api/v1/events/{eid}/archive", json={"reason": "Feierabend"}, headers=_cmd(version=4)
    )
    assert arch.status_code == 200 and arch.json()["status"] == "archived"

    await s.rollback()
    bundle = await _detail(s, eid)
    while_archived = _depth(bundle)

    assert while_active["notes"] == while_archived["notes"]
    assert while_active["description"] == while_archived["description"] == "Bahnsteig 2"
    assert while_active["workflows"] == while_archived["workflows"] == []
    assert while_active["calls"] == while_archived["calls"] == []
    assert while_active["status_history"] == [
        (None, "new"),
        ("new", "accepted"),
        ("accepted", "acknowledged"),
        ("acknowledged", "opened"),
    ]
    assert while_archived["status_history"] == [
        *while_active["status_history"],
        ("opened", "archived"),
    ]
    assert while_archived["domain_events"] == [*while_active["domain_events"], "EVENT_ARCHIVED"]
    assert any(a.action == "EVENT_ARCHIVED" for a in bundle.audit_refs)
    # audit refs are deterministically ordered by time
    times = [a.occurred_at_utc for a in bundle.audit_refs]
    assert times == sorted(times)


async def test_archive_detail_unknown_event_is_none(env: tuple) -> None:
    _, s = env
    assert await ArchiveQueryRepository(s).detail(uuid.uuid4()) is None


async def _detail(s: AsyncSession, eid: uuid.UUID) -> ArchiveDetail:
    bundle = await ArchiveQueryRepository(s).detail(eid)
    assert bundle is not None
    return bundle
