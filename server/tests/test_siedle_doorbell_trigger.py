"""DOORBELL_RINGING trigger (roadmap E17-03): a ringing call from a configured
Siedle door station is re-typed ``DOORBELL_RINGING`` with its
``technical_endpoint_id`` filled in; a ring from an unconfigured number stays
``CALL_RINGING`` and, with no rule, goes to the unmapped-source queue.
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

from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.unmapped_signals import UnmappedSignal
from bbz_core.infra.repositories.endpoint_matcher import match_technical_endpoint
from bbz_core.workers.registry import cluster_singletons

_DNIS = "200"
_ROUTE = "RP_TUER"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "doorbell-test-secret-at-least-32-bytes-ok!"
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
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    sess = db  # type: ignore[assignment]
    assert isinstance(sess, AsyncSession)
    yield client, sess


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


async def _seed(s: AsyncSession, *, with_rule: bool = True) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Klingel Haupteingang",
            type="door_station",
            site="Nord",
            default_priority="high",
            popup_text="Klingeln: Haupteingang",
        )
        s.add(ep)
        await s.flush()
        s.add(
            TechnicalEndpointNumber(endpoint_id=ep.id, called_pattern=_DNIS, cti_route_point=_ROUTE)
        )
        if with_rule:
            rule = TriggerRule(
                name="Klingel -> Ereignis",
                endpoint_id=ep.id,
                lifecycle="published",
                priority=1,
            )
            s.add(rule)
            await s.flush()
            s.add(
                TriggerRuleVersion(
                    rule_id=rule.id,
                    version_no=1,
                    lifecycle="published",
                    conditions={
                        "op": "eq",
                        "args": [{"field": "signal_type"}, "DOORBELL_RINGING"],
                    },
                    actions=[
                        {
                            "type": "create_event",
                            "priority": "high",
                            "title": "Klingeln Haupteingang",
                        }
                    ],
                )
            )
        return ep.id


async def _signal_row(s: AsyncSession) -> ProviderEventInbox:
    await s.rollback()
    return (
        await s.execute(
            select(ProviderEventInbox).where(ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one()


async def test_match_technical_endpoint_by_number_route_and_type(s: AsyncSession) -> None:
    eid = await _seed(s, with_rule=False)
    assert await match_technical_endpoint(s, called=_DNIS, types={"door_station"}) == eid
    assert await match_technical_endpoint(s, cti_route_point=_ROUTE, types={"door_station"}) == eid
    assert await match_technical_endpoint(s, called="999", types={"door_station"}) is None
    assert await match_technical_endpoint(s, called=_DNIS, types={"bma"}) is None

    await s.rollback()
    async with s.begin():
        (await s.execute(select(TechnicalEndpoint))).scalar_one().enabled = False
    assert await match_technical_endpoint(s, called=_DNIS, types={"door_station"}) is None


async def test_a_ring_from_a_configured_door_becomes_doorbell_ringing(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _login(client, "cti")
    eid = await _seed(s)

    r = await client.post("/api/v1/telephony/events", json=_ring())
    assert r.status_code == 200 and r.json()["outcome"] == "new"

    sig = await _signal_row(s)
    assert sig.normalized["signal_type"] == "DOORBELL_RINGING"
    assert sig.normalized["source"]["technical_endpoint_id"] == str(eid)

    assert await _trigger_tick() >= 1
    event = (await s.execute(select(Event))).scalars().one()
    assert event.title == "Klingeln Haupteingang" and event.priority == "high"


async def test_a_ring_from_an_unconfigured_number_stays_call_ringing_and_goes_unmapped(
    env: tuple,
) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _login(client, "cti")
    await _seed(s)

    await client.post("/api/v1/telephony/events", json=_ring(called_number="999"))
    sig = await _signal_row(s)
    assert sig.normalized["signal_type"] == "CALL_RINGING"

    await _trigger_tick()
    assert (await s.execute(select(func.count()).select_from(Event))).scalar_one() == 0
    assert (await s.execute(select(func.count()).select_from(UnmappedSignal))).scalar_one() == 1


async def test_a_duplicate_ring_is_one_doorbell_signal(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cti", ["calls.ingest_provider_events"])
    await _login(client, "cti")
    await _seed(s)

    event = _ring()
    await client.post("/api/v1/telephony/events", json=event)
    await client.post("/api/v1/telephony/events", json=event)  # same id / call+type

    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(ProviderEventInbox)
            .where(ProviderEventInbox.dedupe_key.like("signal:%"))
        )
    ).scalar_one()
    assert n == 1

    await _trigger_tick()
    assert (await s.execute(select(func.count()).select_from(Event))).scalar_one() == 1
