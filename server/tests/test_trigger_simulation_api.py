"""Trigger simulation: dry-run a synthetic signal, report matches + planned
actions, zero real effect, one TRIGGER_SIMULATED audit row (E15-11)."""

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
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.trigger_rules import TriggerExecution, TriggerRule, TriggerRuleVersion

_MANAGE = ["technical_endpoints.view", "technical_endpoints.manage"]

_PANIC: dict[str, Any] = {
    "signal_type": "PANIC_ALARM_RAISED",
    "provider": "panic_mock",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"external_source_id": "panic-flur-1", "severity": "critical"},
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "trsim-test-secret-at-least-32-bytes-okoko!"
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


async def _published_rule(
    s: AsyncSession, *, name: str, conditions: dict[str, Any], actions: list[dict[str, Any]]
) -> None:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name=name, lifecycle="published", priority=10)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions=conditions,
                actions=actions,
            )
        )


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_simulating_a_panic_signal_reports_the_rule_with_no_real_effect(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sim", _MANAGE)
    await _login(client, "sim")
    await _published_rule(
        s,
        name="Panik → kritisches Ereignis",
        conditions={"op": "eq", "args": [{"field": "signal_type"}, "PANIC_ALARM_RAISED"]},
        actions=[
            {"type": "create_event", "priority": "critical"},
            {"type": "attach_workflow", "template_key": "panik"},
            {"type": "notify", "payload": {"channel": "leitstelle"}},
        ],
    )

    r = await client.post("/api/v1/trigger-rules/simulate", json={"signal": _PANIC})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["executed"] is False
    assert body["signal_type"] == "PANIC_ALARM_RAISED"
    assert len(body["matched"]) == 1
    m = body["matched"][0]
    assert m["rule_name"] == "Panik → kritisches Ereignis"
    assert [a["type"] for a in m["actions"]] == ["create_event", "attach_workflow", "notify"]
    assert body["planned_action_count"] == 3

    # zero real effect
    assert await _count(s, Event) == 0
    assert await _count(s, ExternalActionOutbox) == 0
    assert await _count(s, ProviderEventInbox) == 0
    assert await _count(s, TriggerExecution) == 0
    # exactly one audit trace
    await s.rollback()
    audits = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "TRIGGER_SIMULATED")))
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].after["planned_action_count"] == 3


async def test_a_signal_matching_no_rule_reports_nothing_matched(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sim2", _MANAGE)
    await _login(client, "sim2")
    await _published_rule(
        s,
        name="nur Türklingel",
        conditions={"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]},
        actions=[{"type": "notify"}],
    )

    r = await client.post("/api/v1/trigger-rules/simulate", json={"signal": _PANIC})
    assert r.status_code == 200
    assert r.json()["matched"] == [] and r.json()["planned_action_count"] == 0
    assert await _audit_count(s, "TRIGGER_SIMULATED") == 1  # still audited


async def test_a_dtmf_code_never_appears_in_the_report(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sim3", _MANAGE)
    await _login(client, "sim3")
    # a published version that somehow carries a code (the publish gate blocks
    # this, but the report must scrub defensively)
    await _published_rule(
        s,
        name="Tür",
        conditions={},
        actions=[{"type": "send_dtmf_profile", "dtmf_profile_id": "haupttor", "code": "1234#"}],
    )

    r = await client.post("/api/v1/trigger-rules/simulate", json={"signal": _PANIC})
    assert r.status_code == 200
    assert "1234" not in r.text
    action = r.json()["matched"][0]["actions"][0]
    assert action["dtmf_profile_id"] == "haupttor"
    assert "code" not in action and "dtmf" not in action


async def test_an_invalid_signal_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sim4", _MANAGE)
    await _login(client, "sim4")
    r = await client.post(
        "/api/v1/trigger-rules/simulate", json={"signal": {"signal_type": "NOPE"}}
    )
    assert r.status_code == 422


async def test_simulation_requires_manage_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["technical_endpoints.view"])
    await _login(client, "viewer")
    r = await client.post("/api/v1/trigger-rules/simulate", json={"signal": _PANIC})
    assert r.status_code == 403
