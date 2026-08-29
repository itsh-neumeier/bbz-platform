"""Every critical action is wired to an audit write (E04-03 contract)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import CRITICAL_ACTIONS
from bbz_core.infra.models.audit import AuditEvent

_BBZ_CORE = Path(__file__).resolve().parents[1] / "bbz_core"


def test_every_critical_action_is_emitted_from_a_write_path() -> None:
    """A critical action must appear next to an ``AuditService(`` call somewhere
    under ``bbz_core`` — declaring it in the enum is not enough."""
    wired: set[str] = set()
    for path in _BBZ_CORE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "AuditService(" not in text:
            continue
        for name in (a.name for a in CRITICAL_ACTIONS):
            if f"AuditAction.{name}" in text:
                wired.add(name)
    missing = {a.name for a in CRITICAL_ACTIONS} - wired
    assert not missing, f"critical actions with no audit call: {sorted(missing)}"


# --- integration: each event-side critical action writes exactly one row ------


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "audcrit-test-secret-at-least-32-bytes-ok!!"
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


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _cmd(*, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _audit_count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_assign_writes_exactly_one_audit_row_with_diff(env: tuple) -> None:
    client, s = env
    disp = await _make_user(s, "disp", ["events.create", "events.assign"])
    target = await _make_user(s, "target", [])
    await _login(client, "disp")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "high"}, headers=_cmd())
    ).json()["id"]

    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(target)},
        headers=_cmd(version=1),
    )
    assert r.status_code == 200, r.text
    row = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "EVENT_ASSIGNED"))
    ).scalar_one()
    assert row.actor_user_id == disp
    assert row.target_id == eid
    assert row.before["assignee_id"] is None
    assert row.after["assignee_id"] == str(target)


async def test_export_is_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "exp", ["events.create", "events.export"])
    await _login(client, "exp")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    ).json()["id"]

    assert (await client.get(f"/api/v1/events/{eid}/export")).status_code == 200
    assert await _audit_count(s, "EVENT_EXPORTED") == 1
