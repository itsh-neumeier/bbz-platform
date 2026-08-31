"""Siedle door-station endpoint profile (roadmap E17-01): the technical-endpoint
admin API carries the door-open DTMF **profile reference** (id only, never a
code), the operator popup text and the door-open timeout; touching those needs
`door.configure` on top of `technical_endpoints.manage`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint

_FULL = ["technical_endpoints.view", "technical_endpoints.manage", "door.configure"]
_NO_DOOR = ["technical_endpoints.view", "technical_endpoints.manage"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "siedle-ep-test-secret-at-least-32-bytes-x!"
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


_PROFILE_ID = str(uuid.uuid4())


def test_the_door_station_columns_exist_and_are_nullable() -> None:
    cols = Base.metadata.tables["technical_endpoints"].columns
    for name in ("dtmf_profile_id", "popup_text", "door_open_timeout_seconds"):
        assert name in cols and cols[name].nullable


async def _door_profile(s: AsyncSession) -> str:
    """A door_action_profile the endpoint can reference (E17-02 FK). The
    ciphertext content is irrelevant to this test — no key needed."""
    from bbz_core.infra.models.door_action_profiles import DoorActionProfile

    await s.rollback()
    async with s.begin():
        p = DoorActionProfile(name=f"p-{uuid.uuid4().hex[:6]}", dtmf_ciphertext="stub")
        s.add(p)
        await s.flush()
        return str(p.id)


async def test_a_door_station_profile_round_trips(env: tuple) -> None:
    client, s = env
    await _make_user(s, "dsa", _FULL)
    await _login(client, "dsa")
    profile_id = await _door_profile(s)

    r = await client.post(
        "/api/v1/technical-endpoints",
        json={
            "name": "Klingel Haupteingang",
            "type": "door_station",
            "site": "Nord",
            "dtmf_profile_id": profile_id,
            "popup_text": "Klingeln: Haupteingang",
            "door_open_timeout_seconds": 20,
            "numbers": [{"called_pattern": "200", "cti_route_point": "RP_TUER"}],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dtmf_profile_id"] == profile_id
    assert body["popup_text"] == "Klingeln: Haupteingang"
    assert body["door_open_timeout_seconds"] == 20

    got = (await client.get(f"/api/v1/technical-endpoints/{body['id']}")).json()
    assert got["dtmf_profile_id"] == profile_id

    patched = await client.patch(
        f"/api/v1/technical-endpoints/{body['id']}",
        json={"door_open_timeout_seconds": 15},
    )
    assert patched.status_code == 200 and patched.json()["door_open_timeout_seconds"] == 15
    assert await _audit_count(s, "TECHNICAL_ENDPOINT_UPDATED") == 1


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


@pytest.mark.parametrize("bad_key", ["dtmf_code", "code", "dtmf", "dtmf_secret"])
async def test_a_raw_dtmf_code_in_the_body_is_rejected(env: tuple, bad_key: str) -> None:
    client, s = env
    await _make_user(s, f"dsx{len(bad_key)}", _FULL)
    await _login(client, f"dsx{len(bad_key)}")

    r = await client.post(
        "/api/v1/technical-endpoints",
        json={"name": "T", "type": "door_station", bad_key: "1234#"},
    )
    assert r.status_code == 422  # extra="forbid" — a code never reaches the model
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(TechnicalEndpoint))).scalar_one() == 0


async def test_door_config_is_required_for_a_door_station(env: tuple) -> None:
    client, s = env
    await _make_user(s, "nod", _NO_DOOR)
    await _login(client, "nod")

    r = await client.post(
        "/api/v1/technical-endpoints", json={"name": "Tor", "type": "door_station"}
    )
    assert r.status_code == 403 and "door.configure" in r.text

    # a non-door endpoint is unaffected by the new guard
    ok = await client.post("/api/v1/technical-endpoints", json={"name": "BMA 7", "type": "bma"})
    assert ok.status_code == 201


async def test_door_config_is_required_to_add_a_profile_ref_to_any_endpoint(env: tuple) -> None:
    client, s = env
    await _make_user(s, "nod2", _NO_DOOR)
    await _login(client, "nod2")

    created = await client.post(
        "/api/v1/technical-endpoints", json={"name": "V", "type": "video_alarm"}
    )
    assert created.status_code == 201
    r = await client.patch(
        f"/api/v1/technical-endpoints/{created.json()['id']}",
        json={"dtmf_profile_id": _PROFILE_ID},
    )
    assert r.status_code == 403 and "door.configure" in r.text


@pytest.mark.parametrize("bad", [0, -1, 601, 10000])
async def test_the_timeout_is_bounded(env: tuple, bad: int) -> None:
    client, s = env
    await _make_user(s, f"tmo{bad}", _FULL)
    await _login(client, f"tmo{bad}")
    r = await client.post(
        "/api/v1/technical-endpoints",
        json={"name": "T", "type": "door_station", "door_open_timeout_seconds": bad},
    )
    assert r.status_code == 422
