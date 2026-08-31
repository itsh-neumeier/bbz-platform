"""Siedle ring flow (roadmap E17-04): on DOORBELL_RINGING a time-limited
"Klingeln: <name>" popup is shown at the bound workplace and the associated
camera is requested independently — a Coda outage never blocks the popup.

Backend compose over E17-03 + E15-06/14 + E15-07/E16-08. The Playwright leg is
deferred to the frontend phase (Epic 07), like E15-14.
"""

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

from bbz_core.infra.db import get_sessionmaker
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.integrations_host.providers import reset_provider_cache
from bbz_core.workers import camera_handlers
from bbz_core.workers.registry import cluster_singletons

_DNIS = "200"
_WORKPLACE = "33333333-3333-3333-3333-333333333333"
_OTHER_WP = "44444444-4444-4444-4444-444444444444"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "ring-popup-test-secret-at-least-32-bytes-x"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture(autouse=True)
def _clean_provider_cache() -> Iterator[None]:
    reset_provider_cache()
    yield
    reset_provider_cache()


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


def _ring(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "Ring",
        "event_type": "CALL_RINGING",
        "occurred_at": now,
        "received_at": now,
        "source_call_id": f"c-{uuid.uuid4().hex[:6]}",
        "gateway_node": "BBZ-SRV01",
        "called_number": _DNIS,
        "calling_number": "+49110",
    }
    base.update(kw)
    return base


async def _trigger_tick() -> int:
    tick = next(spec.tick for spec in cluster_singletons() if spec.name == "trigger-engine")
    result = await tick()
    assert isinstance(result, int)
    return result


async def _outbox_tick() -> int:
    tick = next(spec.tick for spec in cluster_singletons() if spec.name == "outbox-dispatcher")
    result = await tick()
    assert isinstance(result, int)
    return result


async def _seed(s: AsyncSession) -> None:
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Klingel Haupteingang",
            type="door_station",
            popup_text="Klingeln: Haupteingang",
        )
        s.add(ep)
        await s.flush()
        s.add(TechnicalEndpointNumber(endpoint_id=ep.id, called_pattern=_DNIS))
        rule = TriggerRule(
            name="Klingel-Popup + Kamera", endpoint_id=ep.id, lifecycle="published", priority=1
        )
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]},
                actions=[
                    {
                        "type": "show_client_popup",
                        "workplace_id": _WORKPLACE,
                        "kind": "doorbell",
                        "payload": {"actions": ["open", "reject"]},
                    },
                    {
                        "type": "open_camera_group",
                        "camera_refs": ["CAM-TUER-1", "CAM-TUER-2"],
                        "workplace_id": _WORKPLACE,
                    },
                ],
            )
        )


async def test_a_ring_shows_the_doorbell_popup_and_requests_the_camera(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _make_user(s, "op", ["events.view"])
    await _seed(s)

    await _login(client, "cti")
    assert (await client.post("/api/v1/telephony/events", json=_ring())).status_code == 200
    assert await _trigger_tick() >= 1

    await _login(client, "op")
    popups = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()
    assert len(popups) == 1
    assert popups[0]["kind"] == "doorbell"
    assert popups[0]["payload"]["text"] == "Klingeln: Haupteingang"  # auto-filled (E17-04)
    assert popups[0]["payload"]["actions"] == ["open", "reject"]
    assert _dt.datetime.fromisoformat(popups[0]["expires_at"]) > _dt.datetime.now(_dt.UTC)
    assert "dtmf" not in str(popups[0]).lower() and "secret" not in str(popups[0]).lower()

    # nothing at another workplace
    assert (await client.get(f"/api/v1/client/popups?workplace_id={_OTHER_WP}")).json() == []

    # the camera group is a decoupled outbox side effect
    await s.rollback()
    cam = (
        (
            await s.execute(
                select(ExternalActionOutbox).where(
                    ExternalActionOutbox.action_type == "open_camera_group"
                )
            )
        )
        .scalars()
        .one()
    )
    assert cam.payload["camera_refs"] == ["CAM-TUER-1", "CAM-TUER-2"]
    raised = (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "CLIENT_POPUP_RAISED")
        )
    ).scalar_one()
    assert raised == 1
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "TRIGGER_EXECUTED")
        )
    ).scalar_one() == 2


async def test_a_camera_outage_does_not_block_the_popup(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _make_user(s, "op", ["events.view"])
    await _seed(s)

    from bbz_integration_sdk.providers.video_types import VideoProviderError

    async def _down() -> Any:
        raise VideoProviderError("coda down")

    monkeypatch.setattr(camera_handlers, "active_video_provider", _down)

    await _login(client, "cti")
    await client.post("/api/v1/telephony/events", json=_ring())
    await _trigger_tick()

    # drive the camera row to its terminal failure
    for _ in range(20):
        async with get_sessionmaker()() as w, w.begin():
            row = (
                await w.execute(
                    select(ExternalActionOutbox).where(
                        ExternalActionOutbox.action_type == "open_camera_group"
                    )
                )
            ).scalar_one()
            if row.status == "failed":
                break
            row.next_attempt_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=1)
        await _outbox_tick()

    async with get_sessionmaker()() as r:
        cam = (await r.execute(select(ExternalActionOutbox))).scalar_one()
    assert cam.status == "failed"

    # the popup is still there and unaffected
    await _login(client, "op")
    popups = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()
    assert len(popups) == 1 and popups[0]["payload"]["text"] == "Klingeln: Haupteingang"
