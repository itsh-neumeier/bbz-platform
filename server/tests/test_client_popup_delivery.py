"""Client-popup delivery (E15-14 backend): a trigger show_client_popup action
raises a CLIENT_POPUP_RAISED domain event; the bound workplace fetches / confirms
/ dismisses the popup; another workplace never sees it."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_engine import process_signal

_WORKPLACE = uuid.uuid4()
_OTHER_WORKPLACE = uuid.uuid4()

_SIGNAL: dict[str, Any] = {
    "signal_type": "DOORBELL_RINGING",
    "provider": "siedle_mock",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"dnis": "200"},
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "popup-test-secret-at-least-32-bytes-okoko!"
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


async def _popup_rule(s: AsyncSession, *, workplace_id: uuid.UUID, ttl_seconds: int = 120) -> None:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name="Klingel-Popup", lifecycle="published", priority=10)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={},
                actions=[
                    {
                        "type": "show_client_popup",
                        "workplace_id": str(workplace_id),
                        "kind": "doorbell",
                        "ttl_seconds": ttl_seconds,
                        "payload": {"caller": "Tor Süd"},
                    }
                ],
            )
        )


async def _fire(s: AsyncSession, *, event_id: str = "evt-1") -> None:
    await process_signal(s, signal=_SIGNAL, provider_event_id=event_id)


async def test_a_trigger_popup_raises_a_domain_event_bound_to_the_workplace(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view"])
    await _login(client, "op")
    await _popup_rule(s, workplace_id=_WORKPLACE)
    await _fire(s)

    await s.rollback()
    popup = (await s.execute(select(ClientPopupEvent))).scalars().one()
    assert popup.workplace_id == _WORKPLACE and popup.kind == "doorbell"

    raised = (
        (
            await s.execute(
                select(DomainEvent).where(DomainEvent.event_type == "CLIENT_POPUP_RAISED")
            )
        )
        .scalars()
        .all()
    )
    assert len(raised) == 1
    assert raised[0].payload["workplace_id"] == str(_WORKPLACE)
    assert raised[0].payload["popup_id"] == str(popup.id)

    listed = await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["payload"] == {"caller": "Tor Süd"}

    # another workplace sees nothing
    other = await client.get(f"/api/v1/client/popups?workplace_id={_OTHER_WORKPLACE}")
    assert other.json() == []


async def test_delivered_is_audited_once_then_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view"])
    await _login(client, "op")
    await _popup_rule(s, workplace_id=_WORKPLACE)
    await _fire(s)
    pid = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()[0]["id"]

    r1 = await client.post(f"/api/v1/client/popups/{pid}/delivered?workplace_id={_WORKPLACE}")
    assert r1.status_code == 200 and r1.json()["delivered_at"] is not None
    r2 = await client.post(f"/api/v1/client/popups/{pid}/delivered?workplace_id={_WORKPLACE}")
    assert r2.status_code == 200
    assert await _audit_count(s, "CLIENT_POPUP_DELIVERED") == 1  # not twice


async def test_dismiss_removes_it_from_the_pending_list(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view"])
    await _login(client, "op")
    await _popup_rule(s, workplace_id=_WORKPLACE)
    await _fire(s)
    pid = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()[0]["id"]

    d = await client.post(f"/api/v1/client/popups/{pid}/dismiss?workplace_id={_WORKPLACE}")
    assert d.status_code == 200 and d.json()["dismissed_at"] is not None
    assert (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json() == []


async def test_an_expired_popup_is_not_listed(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view"])
    await _login(client, "op")
    await _popup_rule(s, workplace_id=_WORKPLACE, ttl_seconds=1)
    await _fire(s)

    await s.rollback()
    async with s.begin():
        row = (await s.execute(select(ClientPopupEvent))).scalars().one()
        row.expires_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=5)

    assert (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json() == []


async def test_acting_on_a_popup_bound_to_another_workplace_is_403(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.view"])
    await _login(client, "op")
    await _popup_rule(s, workplace_id=_WORKPLACE)
    await _fire(s)
    pid = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()[0]["id"]

    r = await client.post(f"/api/v1/client/popups/{pid}/delivered?workplace_id={_OTHER_WORKPLACE}")
    assert r.status_code == 403


async def test_events_view_permission_is_required(env: tuple) -> None:
    client, s = env
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    r = await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")
    assert r.status_code == 403
