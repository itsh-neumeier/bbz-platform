"""Per-alarm-source admin API: upsert endpoint + cameras in one place, default
critical priority for panic buttons, both perms required, audited (E16-06)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.integration_camera_mappings import IntegrationCameraMapping
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint

_MANAGE = ["technical_endpoints.view", "technical_endpoints.manage", "integrations.configure"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "coda-src-test-secret-at-least-32-bytes-ok!"
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


def _body(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "endpoint_name": "Ueberfalltaster ServicePoint Nuernberg Hbf",
        "endpoint_type": "panic_button",
        "site": "Nuernberg Hbf",
        "camera_refs": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
        "popup_profile": "panic",
        "workflow_selection_policy": {"mode": "latest_published", "template_key": "ueberfall"},
        "escalation_profile": "leitstelle",
    }
    base.update(kw)
    return base


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_put_creates_endpoint_and_cameras_and_defaults_panic_to_critical(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cs1", _MANAGE)
    await _login(client, "cs1")

    r = await client.put("/api/v1/coda-alarm-sources/CODA-ALARM-4711", json=_body())
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["priority"] == "critical"  # panic_button default (§36)
    assert out["camera_refs"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]
    assert out["endpoint_type"] == "panic_button" and out["site"] == "Nuernberg Hbf"

    await s.rollback()
    endpoints = (await s.execute(select(TechnicalEndpoint))).scalars().all()
    assert len(endpoints) == 1 and endpoints[0].provider_id == "coda_video"
    cams = (await s.execute(select(IntegrationCameraMapping))).scalars().all()
    assert {c.camera_external_ref for c in cams} == {"CAM-SP-NBG-01", "CAM-SP-NBG-02"}
    assert all(c.alarm_source_external_id == "CODA-ALARM-4711" for c in cams)
    assert await _audit_count(s, "CODA_ALARM_SOURCE_CONFIGURED") == 1


async def test_an_explicit_priority_overrides_the_panic_default(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cs2", _MANAGE)
    await _login(client, "cs2")
    r = await client.put(
        "/api/v1/coda-alarm-sources/SRC-A", json=_body(priority="high", camera_refs=[])
    )
    assert r.status_code == 200 and r.json()["priority"] == "high"


async def test_put_is_idempotent_and_replaces_the_camera_list(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cs3", _MANAGE)
    await _login(client, "cs3")

    await client.put("/api/v1/coda-alarm-sources/SRC-B", json=_body())
    r2 = await client.put("/api/v1/coda-alarm-sources/SRC-B", json=_body(camera_refs=["CAM-9"]))
    assert r2.status_code == 200 and r2.json()["camera_refs"] == ["CAM-9"]

    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(TechnicalEndpoint))).scalar_one() == 1
    cams = (await s.execute(select(IntegrationCameraMapping))).scalars().all()
    assert [c.camera_external_ref for c in cams] == ["CAM-9"]
    assert r2.json()["active_config_version"] == 2


async def test_get_and_list_and_delete(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cs4", _MANAGE)
    await _login(client, "cs4")
    await client.put("/api/v1/coda-alarm-sources/SRC-C", json=_body())

    assert (await client.get("/api/v1/coda-alarm-sources/SRC-C")).json()["site"] == "Nuernberg Hbf"
    assert len((await client.get("/api/v1/coda-alarm-sources")).json()) == 1

    d = await client.delete("/api/v1/coda-alarm-sources/SRC-C")
    assert d.status_code == 204
    assert (await client.get("/api/v1/coda-alarm-sources/SRC-C")).status_code == 404
    await s.rollback()
    assert (
        await s.execute(select(func.count()).select_from(IntegrationCameraMapping))
    ).scalar_one() == 0
    assert await _audit_count(s, "CODA_ALARM_SOURCE_REMOVED") == 1


async def test_configure_needs_both_manage_and_integrations_configure(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cs5", ["technical_endpoints.view", "technical_endpoints.manage"])
    await _login(client, "cs5")
    r = await client.put("/api/v1/coda-alarm-sources/SRC-D", json=_body())
    assert r.status_code == 403
    assert "integrations.configure" in r.text
