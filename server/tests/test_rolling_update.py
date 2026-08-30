"""Rolling-update marker endpoint + the operator script's guard rails (E06-09)."""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent

_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "rolling-update.sh"
_RUNBOOK = Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "rolling-update.md"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "roll-test-secret-at-least-32-bytes-okokok!!"
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


async def _count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_marker_needs_cluster_manage_and_audits_both_phases(env: tuple) -> None:
    client, s = env
    assert (
        await client.post("/api/v1/system/rolling-update", json={"phase": "started", "image": "x"})
    ).status_code == 401

    await _make_user(s, "viewer", ["system.cluster.view"])
    await _login(client, "viewer")
    assert (
        await client.post(
            "/api/v1/system/rolling-update", json={"phase": "started", "image": "x@sha256:aa"}
        )
    ).status_code == 403

    await _make_user(s, "op", ["system.cluster.manage"])
    await _login(client, "op")
    img = "ghcr.io/x/bbz-api@sha256:deadbeef"
    r1 = await client.post("/api/v1/system/rolling-update", json={"phase": "started", "image": img})
    assert r1.status_code == 202 and r1.json()["image"] == img
    r2 = await client.post(
        "/api/v1/system/rolling-update",
        json={"phase": "completed", "image": img, "notes": "window 20:00-20:15"},
    )
    assert r2.status_code == 202

    assert await _count(s, "ROLLING_UPDATE_STARTED") == 1
    assert await _count(s, "ROLLING_UPDATE_COMPLETED") == 1
    row = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "ROLLING_UPDATE_COMPLETED"))
    ).scalar_one()
    assert row.after == {"phase": "completed", "image": img}
    assert row.reason == "window 20:00-20:15"


async def test_marker_rejects_an_unknown_phase(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", ["system.cluster.manage"])
    await _login(client, "op2")
    r = await client.post(
        "/api/v1/system/rolling-update", json={"phase": "halfway", "image": "x@sha256:a"}
    )
    assert r.status_code == 422


@pytest.mark.skipif(not _SCRIPT.exists(), reason="script missing")
def test_rolling_update_script_is_valid_and_refuses_a_tag() -> None:
    assert subprocess.run(["sh", "-n", str(_SCRIPT)]).returncode == 0

    env = {
        "PATH": os.environ["PATH"],
        "NODES": "n2 n1",
        "IMAGE": "ghcr.io/x/bbz-api:latest",  # a tag, not a digest
        "API": "http://127.0.0.1:1",
        "TOKEN": "t",
    }
    done = subprocess.run(["sh", str(_SCRIPT)], env=env, capture_output=True, text=True)
    assert done.returncode == 2
    assert "pinned by digest" in done.stdout + done.stderr


def test_runbook_documents_the_order_and_abort() -> None:
    rb = _RUNBOOK.read_text(encoding="utf-8")
    assert "passive/standby first" in rb.lower() or "passive node first" in rb.lower()
    assert "migration-compat" in rb and "abort" in rb.lower()
    assert "ROLLING_UPDATE_STARTED" in rb and "ROLLING_UPDATE_COMPLETED" in rb
