"""§35 "Siedle / Cayuga" end-to-end (roadmap E17-07).

The full 10-step scenario over the compose stack + the mocks:

1. a Siedle call arrives (``POST /api/v1/telephony/events``, ``CALL_RINGING``)
2. the technical number is recognised → the signal is re-typed ``DOORBELL_RINGING``
3. the Cayuga camera action is dispatched (decoupled outbox side effect)
4. the BBZ ring popup appears at the bound workplace
5. the operator presses "Öffnen" (``POST /api/v1/doors/{id}/open``)
6. the call is answered (it was still ringing)
7. the DTMF profile is sent **exactly once**
8. the call is automatically ended
9. the audit trail carries the profile id, **never** the DTMF code
10. a duplicate provider event / a repeated command opens the door only once

No new production code — proves E17-01…06 + E15/E16 compose under the HA rules.
"""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.door_open_commands import DoorOpenCommand
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.door_action_profiles import DoorActionProfileService
from bbz_core.integrations_host.providers import active_telephony_provider, reset_provider_cache
from bbz_core.workers.registry import cluster_singletons

_DNIS = "200"
_WORKPLACE = "55555555-5555-5555-5555-555555555555"
_CODE = "42B#42"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "e2e-siedle-secret-at-least-32-bytes-okok!!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_DOOR_DTMF_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    os.environ.pop("BBZ_DOOR_DTMF_ENCRYPTION_KEY", None)


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


def _ring(call_id: str, **kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:10]}",
        "provider": "telephony_mock",
        "raw_event_type": "Ring",
        "event_type": "CALL_RINGING",
        "occurred_at": now,
        "received_at": now,
        "source_call_id": call_id,
        "gateway_node": "BBZ-SRV01",
        "called_number": _DNIS,
        "calling_number": "+49110",
    }
    base.update(kw)
    return base


async def _tick(name: str) -> int:
    fn = next(spec.tick for spec in cluster_singletons() if spec.name == name)
    result = await fn()
    assert isinstance(result, int)
    return result


async def _seed(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    profile = await DoorActionProfileService(s).create(
        name="Haupttor", dtmf_code=_CODE, post_dtmf_delay_ms=0, auto_hangup=True, actor_id=None
    )
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Klingel Haupteingang",
            type="door_station",
            dtmf_profile_id=profile.id,
            popup_text="Klingeln: Haupteingang",
            door_open_timeout_seconds=5,
        )
        s.add(ep)
        await s.flush()
        s.add(TechnicalEndpointNumber(endpoint_id=ep.id, called_pattern=_DNIS))
        rule = TriggerRule(name="Klingel", endpoint_id=ep.id, lifecycle="published", priority=1)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]},
                actions=[
                    {"type": "show_client_popup", "workplace_id": _WORKPLACE, "kind": "doorbell"},
                    {
                        "type": "open_camera_group",
                        "camera_refs": ["CAM-TUER-1"],
                        "workplace_id": _WORKPLACE,
                    },
                ],
            )
        )
        return ep.id, profile.id


async def test_the_full_siedle_cayuga_flow(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _make_user(s, "op", ["events.view", "door.open", "door.answer"])
    endpoint_id, profile_id = await _seed(s)

    provider = await active_telephony_provider()
    call_id = provider.simulate_incoming(from_number="+49110", to_line=_DNIS)  # type: ignore[attr-defined]

    # 1 + 2 — the call arrives and is recognised as a door station
    await _login(client, "cti")
    r = await client.post("/api/v1/telephony/events", json=_ring(call_id))
    assert r.status_code == 200 and r.json()["outcome"] == "new"

    await s.rollback()
    sig = (
        await s.execute(
            select(ProviderEventInbox).where(ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one()
    assert sig.normalized["signal_type"] == "DOORBELL_RINGING"
    assert sig.normalized["source"]["technical_endpoint_id"] == str(endpoint_id)

    # 3 + 4 — trigger engine: camera dispatched, popup raised
    assert await _tick("trigger-engine") >= 1
    await _login(client, "op")
    popups = (await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()
    assert len(popups) == 1 and popups[0]["kind"] == "doorbell"
    assert popups[0]["payload"]["text"] == "Klingeln: Haupteingang"

    await s.rollback()
    cam = (
        await s.execute(
            select(ExternalActionOutbox).where(
                ExternalActionOutbox.action_type == "open_camera_group"
            )
        )
    ).scalar_one()
    assert cam.payload["camera_refs"] == ["CAM-TUER-1"]

    # 5 + 6 + 7 + 8 — operator opens; answer -> DTMF once -> auto hangup
    cmd = {"X-Command-Id": str(uuid.uuid4())}
    opened = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=cmd
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["outcome"] == "opened" and opened.json()["opened"] is True
    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
    assert await provider.get_active_calls() == []

    # 9 — audit carries the profile id, never the code
    await s.rollback()
    audits = (await s.execute(select(AuditEvent))).scalars().all()
    result_row = next(a for a in audits if a.action == "DOOR_OPEN_RESULT")
    assert result_row.after["door_action_profile_id"] == str(profile_id)
    for a in audits:
        assert _CODE not in f"{a.before}{a.after}{a.reason}"
    for e in (await s.execute(select(DomainEvent))).scalars().all():
        assert _CODE not in str(e.payload)
    for o in (await s.execute(select(ExternalActionOutbox))).scalars().all():
        assert _CODE not in f"{o.payload}{o.result}{o.last_error}"

    # 10a — a duplicate provider event (same call + type) is deduped: no second
    # DOORBELL_RINGING signal, no second popup
    await _login(client, "cti")
    d1 = await client.post("/api/v1/telephony/events", json=_ring(call_id))
    d2 = await client.post("/api/v1/telephony/events", json=_ring(call_id))
    assert d1.json()["outcome"] == "duplicate" and d2.json()["outcome"] == "duplicate"
    await _tick("trigger-engine")
    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(ProviderEventInbox)
            .where(ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one() == 1
    await _login(client, "op")
    assert len((await client.get(f"/api/v1/client/popups?workplace_id={_WORKPLACE}")).json()) == 1

    # 10b — the same command id never opens the door twice
    again = await client.post(
        f"/api/v1/doors/{endpoint_id}/open", json={"call_id": call_id}, headers=cmd
    )
    assert again.json() == opened.json()
    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(DoorOpenCommand))).scalar_one() == 1


async def test_a_coda_outage_never_blocks_the_open(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _make_user(s, "op", ["events.view", "door.open", "door.answer"])
    endpoint_id, _ = await _seed(s)

    from bbz_core.workers import camera_handlers
    from bbz_integration_sdk.providers.video_types import VideoProviderError

    async def _down() -> Any:
        raise VideoProviderError("coda down")

    monkeypatch.setattr(camera_handlers, "active_video_provider", _down)

    provider = await active_telephony_provider()
    call_id = provider.simulate_incoming(from_number="+49110", to_line=_DNIS)  # type: ignore[attr-defined]

    await _login(client, "cti")
    await client.post("/api/v1/telephony/events", json=_ring(call_id))
    await _tick("trigger-engine")
    for _ in range(20):  # drive the camera row to its terminal failure
        if await _tick("outbox-dispatcher") == 0:
            break

    await _login(client, "op")
    opened = await client.post(
        f"/api/v1/doors/{endpoint_id}/open",
        json={"call_id": call_id},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    assert opened.status_code == 200 and opened.json()["outcome"] == "opened"
    assert len(provider._dtmf_sends) == 1  # type: ignore[attr-defined]
