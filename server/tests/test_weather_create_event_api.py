"""Create a BBZ event from a DWD warning (roadmap E18-08): POST
/weather/alerts/{id}/create-event — weather.create_event, idempotent on
X-Command-Id, WEATHER_EVENT_CREATED + EVENT_CREATED, the event links back to the
warning. Never automatic (§10)."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.weather import WeatherAlert
from bbz_core.infra.models.weather_alert_events import WeatherAlertEvent

_NOW = _dt.datetime.now(_dt.UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "weather-evt-test-secret-at-least-32-bytes!!"
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


async def _alert(s: AsyncSession, source_ref: str = "cap-1") -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        a = WeatherAlert(
            region="Nürnberg",
            type="Sturmböen",
            level="3",
            valid_from=_NOW,
            valid_to=_NOW + _dt.timedelta(hours=6),
            headline="Amtliche WARNUNG vor schweren Sturmböen",
            description="Böen 90 km/h aus Südwest.",
            source_ref=source_ref,
            received_at=_NOW,
        )
        s.add(a)
        await s.flush()
        return a.id


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def test_create_event_requires_the_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["weather.view"])
    alert_id = await _alert(s)
    await _login(client, "viewer")
    r = await client.post(
        f"/api/v1/weather/alerts/{alert_id}/create-event",
        json={"priority": "high"},
        headers=_cmd(),
    )
    assert r.status_code == 403


async def test_a_warning_becomes_a_linked_event_and_is_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view", "weather.create_event"])
    alert_id = await _alert(s)
    await _login(client, "op")

    r = await client.post(
        f"/api/v1/weather/alerts/{alert_id}/create-event",
        json={"priority": "high", "assessment": "Betrieb: Kräne einfahren, Streife informieren."},
        headers=_cmd(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True and body["priority"] == "high"
    assert body["source_ref"] == "cap-1"
    event_id = uuid.UUID(body["event_id"])

    await s.rollback()
    ev = (await s.execute(select(Event).where(Event.id == event_id))).scalar_one()
    assert ev.source == "weather" and ev.priority == "high"
    assert ev.title.startswith("Amtliche WARNUNG")
    assert "Kräne einfahren" in (ev.description or "")

    link = (await s.execute(select(WeatherAlertEvent))).scalar_one()
    assert link.event_id == event_id and link.weather_alert_id == alert_id
    assert link.source_ref == "cap-1" and link.assessment is not None

    audit = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "WEATHER_EVENT_CREATED"))
    ).scalar_one()
    assert audit.target_id == str(event_id)
    assert audit.after["weather_alert_id"] == str(alert_id)
    assert audit.after["source_ref"] == "cap-1" and audit.after["region"] == "Nürnberg"

    # the event's own EVENT_CREATED domain event still fires
    assert (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "EVENT_CREATED")
        )
    ).scalar_one() == 1


async def test_the_same_command_id_makes_exactly_one_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view", "weather.create_event"])
    alert_id = await _alert(s)
    await _login(client, "op")

    headers = _cmd()
    payload = {"priority": "medium", "assessment": "x"}
    first = await client.post(
        f"/api/v1/weather/alerts/{alert_id}/create-event", json=payload, headers=headers
    )
    second = await client.post(
        f"/api/v1/weather/alerts/{alert_id}/create-event", json=payload, headers=headers
    )
    assert first.json()["event_id"] == second.json()["event_id"]

    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(Event))).scalar_one() == 1
    assert (await s.execute(select(func.count()).select_from(WeatherAlertEvent))).scalar_one() == 1


async def test_an_unknown_alert_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view", "weather.create_event"])
    await _login(client, "op")
    r = await client.post(
        f"/api/v1/weather/alerts/{uuid.uuid4()}/create-event",
        json={"priority": "low"},
        headers=_cmd(),
    )
    assert r.status_code == 404
