"""Weather API (roadmap E18-07): read-only DWD data for the Wetterlage page —
alerts / observations / radar / regions, each with the refresh health, all
`weather.view`-gated, all times UTC."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation

_NOW = _dt.datetime.now(_dt.UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "weather-api-test-secret-at-least-32-bytes!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture(autouse=True)
def _clear_radar_cache() -> Iterator[None]:
    """The radar frame cache is a per-node module global — keep tests hermetic."""
    from bbz_core.infra.repositories.weather_read import RADAR_CACHE

    RADAR_CACHE.clear()
    yield
    RADAR_CACHE.clear()


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


async def _seed(s: AsyncSession) -> None:
    await s.rollback()
    async with s.begin():
        s.add(
            WeatherAlert(
                region="Nürnberg",
                type="Sturmböen",
                level="2",
                valid_from=_NOW,
                valid_to=_NOW + _dt.timedelta(hours=6),
                headline="Amtliche Warnung vor Sturmböen",
                description="Böen 70 km/h.",
                source_ref="cap-1",
                received_at=_NOW,
            )
        )
        s.add(
            WeatherAlert(
                region="Fürth", type="Gewitter", level="1", source_ref="cap-2", received_at=_NOW
            )
        )
        for hours, value in ((2, 16.0), (1, 17.5)):  # newest is 17.5
            s.add(
                WeatherObservation(
                    place="Erlangen",
                    metric="temperature",
                    value=value,
                    unit="°C",
                    observed_at=_NOW - _dt.timedelta(hours=hours),
                    station_ref="10763",
                )
            )


async def test_all_routes_require_weather_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "plain", [])
    await _login(client, "plain")
    for path in ("/weather/alerts", "/weather/observations", "/weather/radar", "/weather/regions"):
        assert (await client.get(f"/api/v1{path}")).status_code == 403


async def test_alerts_come_back_with_health_and_utc_times(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view"])
    await _seed(s)
    await _login(client, "op")

    body = (await client.get("/api/v1/weather/alerts")).json()
    assert body["attribution"] == "Deutscher Wetterdienst"
    assert body["health"]["overall"] in {"ok", "stale", "degraded", "down"}
    assert {k["data_kind"] for k in body["health"]["kinds"]} == {
        "warnings",
        "radar",
        "observations",
    }
    assert len(body["alerts"]) == 2
    a = next(x for x in body["alerts"] if x["region"] == "Nürnberg")
    assert a["type"] == "Sturmböen" and a["source_ref"] == "cap-1"
    assert a["valid_from"].endswith("+00:00") or a["valid_from"].endswith("Z")

    filtered = (await client.get("/api/v1/weather/alerts?region=Fürth")).json()["alerts"]
    assert [x["region"] for x in filtered] == ["Fürth"]


async def test_observations_are_the_latest_per_place_and_metric(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view"])
    await _seed(s)
    await _login(client, "op")

    obs = (await client.get("/api/v1/weather/observations")).json()["observations"]
    assert len(obs) == 1
    assert obs[0]["place"] == "Erlangen" and obs[0]["value"] == 17.5


async def test_radar_is_empty_before_the_first_refresh_but_still_reports_health(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view"])
    await _login(client, "op")
    body = (await client.get("/api/v1/weather/radar?area=mittelfranken")).json()
    assert body["area"] == "mittelfranken" and body["frames"] == []
    assert "overall" in body["health"]


async def test_radar_serves_the_cached_frame_series(env: tuple) -> None:
    client, s = env
    from bbz_core.infra.repositories.weather_read import RADAR_CACHE, RadarFrame

    await _make_user(s, "op", ["weather.view"])
    await _login(client, "op")

    t0 = _NOW - _dt.timedelta(minutes=10)
    RADAR_CACHE["mittelfranken"] = [
        RadarFrame(frame_time=t0, image_ref="https://maps.dwd.de/geoserver/dwd/wms?a=1"),
        RadarFrame(frame_time=_NOW, image_ref="https://maps.dwd.de/geoserver/dwd/wms?a=2"),
    ]
    # the default area is the configured one, so ?area= is optional
    body = (await client.get("/api/v1/weather/radar")).json()
    assert body["area"] == "mittelfranken"
    assert [f["image_ref"][-3:] for f in body["frames"]] == ["a=1", "a=2"]
    assert body["frames"][0]["frame_time"].endswith(("Z", "+00:00"))


async def test_regions_lists_what_we_hold_data_for(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["weather.view"])
    await _seed(s)
    await _login(client, "op")
    regions = (await client.get("/api/v1/weather/regions")).json()["regions"]
    assert regions == ["Erlangen", "Fürth", "Nürnberg"]
