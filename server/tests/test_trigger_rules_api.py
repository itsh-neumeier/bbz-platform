"""Trigger-rule admin API: lifecycle draft→validate→publish→retire, validation
errors, immutability, rights, audit (E15-10)."""

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

_MANAGE = ["technical_endpoints.view", "technical_endpoints.manage"]

_COND: dict[str, Any] = {"op": "eq", "args": [{"field": "signal_type"}, "BMA_ALARM_CALL"]}
_ACTIONS: list[dict[str, Any]] = [
    {"type": "create_event", "priority": "critical"},
    {"type": "notify"},
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "traadmin-test-secret-at-least-32-bytes-ok!"
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


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def _new_rule(
    client: httpx.AsyncClient,
    *,
    conditions: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/trigger-rules",
        json={
            "name": f"Regel {uuid.uuid4().hex[:6]}",
            "conditions": _COND if conditions is None else conditions,
            "actions": _ACTIONS if actions is None else actions,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["versions"][0]["id"]


async def test_full_lifecycle_draft_validate_publish_retire(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra", _MANAGE)
    await _login(client, "tra")

    rid, vid = await _new_rule(client)
    assert await _audit_count(s, "TRIGGER_RULE_CREATED") == 1

    v = await client.post(f"/api/v1/trigger-rule-versions/{vid}/validate")
    assert v.status_code == 200
    assert v.json() == {"valid": True, "lifecycle": "validated", "issues": []}
    assert await _audit_count(s, "TRIGGER_RULE_VALIDATED") == 1

    p = await client.post(
        f"/api/v1/trigger-rule-versions/{vid}/publish", json={"changelog": "geht live"}
    )
    assert p.status_code == 200 and p.json()["lifecycle"] == "published"
    assert (await client.get(f"/api/v1/trigger-rules/{rid}")).json()["lifecycle"] == "published"
    assert await _audit_count(s, "TRIGGER_RULE_PUBLISHED") == 1

    # a new version supersedes: publish v2 → v1 retired
    v2 = await client.post(
        f"/api/v1/trigger-rules/{rid}/versions", json={"conditions": {}, "actions": _ACTIONS}
    )
    v2id = v2.json()["id"]
    assert v2.json()["version_no"] == 2
    await client.post(f"/api/v1/trigger-rule-versions/{v2id}/validate")
    await client.post(f"/api/v1/trigger-rule-versions/{v2id}/publish", json={})

    detail = (await client.get(f"/api/v1/trigger-rules/{rid}")).json()
    states = {ver["version_no"]: ver["lifecycle"] for ver in detail["versions"]}
    assert states == {1: "retired", 2: "published"}

    r = await client.post(f"/api/v1/trigger-rule-versions/{v2id}/retire")
    assert r.status_code == 200 and r.json()["lifecycle"] == "retired"
    assert (await client.get(f"/api/v1/trigger-rules/{rid}")).json()["lifecycle"] == "retired"
    assert await _audit_count(s, "TRIGGER_RULE_RETIRED") == 1


async def test_publish_is_refused_without_a_prior_validate(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra2", _MANAGE)
    await _login(client, "tra2")
    _, vid = await _new_rule(client)

    r = await client.post(f"/api/v1/trigger-rule-versions/{vid}/publish", json={})
    assert r.status_code == 409
    assert await _audit_count(s, "TRIGGER_RULE_PUBLISHED") == 0


async def test_validation_reports_bad_conditions_and_actions(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra3", _MANAGE)
    await _login(client, "tra3")

    # unknown DSL field + a DTMF code in an action + an unsupported action type
    _, vid = await _new_rule(
        client,
        conditions={"op": "eq", "args": [{"field": "not_a_field"}, "x"]},
        actions=[
            {"type": "send_dtmf_profile", "dtmf_profile_id": "gate", "code": "1234#"},
            {"type": "open_camera", "camera_id": "c1"},
        ],
    )
    r = await client.post(f"/api/v1/trigger-rule-versions/{vid}/validate")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False and body["lifecycle"] == "draft"
    joined = " | ".join(body["issues"])
    assert "conditions" in joined
    assert "DTMF code" in joined
    assert "not available yet" in joined
    # 1234 must never be echoed back
    assert "1234" not in joined
    assert await _audit_count(s, "TRIGGER_RULE_VALIDATED") == 0


async def test_a_rule_with_no_actions_cannot_be_published(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra4", _MANAGE)
    await _login(client, "tra4")
    _, vid = await _new_rule(client, actions=[])

    r = await client.post(f"/api/v1/trigger-rule-versions/{vid}/validate")
    assert r.json()["valid"] is False
    assert any("at least one action" in i for i in r.json()["issues"])


async def test_a_published_version_cannot_be_edited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra5", _MANAGE)
    await _login(client, "tra5")
    rid, vid = await _new_rule(client)
    await client.post(f"/api/v1/trigger-rule-versions/{vid}/validate")
    await client.post(f"/api/v1/trigger-rule-versions/{vid}/publish", json={})

    r = await client.patch(
        f"/api/v1/trigger-rule-versions/{vid}",
        json={"conditions": {}, "actions": _ACTIONS},
    )
    assert r.status_code == 409
    # and the rule cannot be deleted while it has a published version
    assert (await client.delete(f"/api/v1/trigger-rules/{rid}")).status_code == 409


async def test_a_draft_rule_can_be_deleted(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra6", _MANAGE)
    await _login(client, "tra6")
    rid, _ = await _new_rule(client)
    assert (await client.delete(f"/api/v1/trigger-rules/{rid}")).status_code == 204
    assert (await client.get(f"/api/v1/trigger-rules/{rid}")).status_code == 404


async def test_manage_permission_is_required_for_writes(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["technical_endpoints.view"])
    await _make_user(s, "mgr", _MANAGE)
    await _login(client, "mgr")
    rid, vid = await _new_rule(client)

    await _login(client, "viewer")
    denied = await client.post(
        "/api/v1/trigger-rules", json={"name": "n", "conditions": {}, "actions": []}
    )
    assert denied.status_code == 403
    assert (await client.post(f"/api/v1/trigger-rule-versions/{vid}/validate")).status_code == 403
    assert (await client.get(f"/api/v1/trigger-rules/{rid}")).status_code == 200


async def test_a_bad_endpoint_id_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "tra7", _MANAGE)
    await _login(client, "tra7")
    r = await client.post(
        "/api/v1/trigger-rules",
        json={
            "name": "x",
            "endpoint_id": str(uuid.uuid4()),
            "conditions": {},
            "actions": _ACTIONS,
        },
    )
    assert r.status_code == 422
