"""Two-step reactivation flow + accidental-series guard (E20-05).

No path reactivates without confirm **and** a valid single-use token; a
reactivated event is back in ``queue=active``; a second reactivation within the
cool-down window is refused (429).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent


def _set_cooldown(seconds: int) -> None:
    from bbz_core import settings as settings_mod

    os.environ["BBZ_REACTIVATION_COOLDOWN_SECONDS"] = str(seconds)
    settings_mod.get_settings.cache_clear()


_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.archive",
    "events.reactivate",
    "events.view",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "reactivation-flow-secret-at-least-32-bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ.pop("BBZ_REACTIVATION_COOLDOWN_SECONDS", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_REACTIVATION_COOLDOWN_SECONDS", None)
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


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _archived(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/events", json={"title": "S-Bahn Halt", "priority": "high"}, headers=_cmd()
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        assert (
            await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "Ende"}, headers=_cmd(version=4)
        )
    ).status_code == 200
    return eid


async def _intent(client: httpx.AsyncClient, eid: str) -> str:
    r = await client.post(f"/api/v1/events/{eid}/reactivation-intent")
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def test_full_two_step_reactivation_returns_event_to_the_queue(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _archived(client)

    token = await _intent(client, eid)
    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "Rückfrage Bundespolizei", "token": token},
        headers=_cmd(version=5),
    )
    assert r.status_code == 200 and r.json()["status"] == "opened"

    queue = (await client.get("/api/v1/events?queue=active")).json()["items"]
    assert eid in [i["id"] for i in queue]

    audit = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "EVENT_REACTIVATED"))
    ).scalar_one()
    assert audit.reason == "Rückfrage Bundespolizei"


async def test_reactivate_without_a_token_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl2", _ALL)
    await _login(client, "sl2")
    eid = await _archived(client)
    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "x"},
        headers=_cmd(version=5),
    )
    assert r.status_code == 422
    assert await _reactivated_count(s) == 0


async def test_reactivate_with_a_garbage_token_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl3", _ALL)
    await _login(client, "sl3")
    eid = await _archived(client)
    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "x", "token": "not-a-real-token.aaa"},
        headers=_cmd(version=5),
    )
    assert r.status_code == 422
    assert await _reactivated_count(s) == 0


async def test_token_is_bound_to_the_event_version(env: tuple) -> None:
    client, s = env
    _set_cooldown(0)
    await _make_user(s, "sl4", _ALL)
    await _login(client, "sl4")
    eid = await _archived(client)

    stale = await _intent(client, eid)  # minted for version 5
    ok = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "erste", "token": stale},
        headers=_cmd(version=5),
    )
    assert ok.status_code == 200  # now version 6, opened
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "wieder"}, headers=_cmd(version=6)
        )
    ).status_code == 200

    reused = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "zweite", "token": stale},
        headers=_cmd(version=7),
    )
    assert reused.status_code == 422  # the old token was for version 5


async def test_a_token_from_another_user_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "owner", _ALL)
    await _make_user(s, "other", _ALL)
    await _login(client, "owner")
    eid = await _archived(client)

    await _login(client, "other")
    foreign = await _intent(client, eid)
    await _login(client, "owner")
    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "x", "token": foreign},
        headers=_cmd(version=5),
    )
    assert r.status_code == 422


async def test_second_reactivation_within_cooldown_is_429(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl5", _ALL)
    await _login(client, "sl5")
    eid = await _archived(client)

    first = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "erste", "token": await _intent(client, eid)},
        headers=_cmd(version=5),
    )
    assert first.status_code == 200
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "nochmal"}, headers=_cmd(version=6)
        )
    ).status_code == 200

    again = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "zu schnell", "token": await _intent(client, eid)},
        headers=_cmd(version=7),
    )
    assert again.status_code == 429
    assert await _reactivated_count(s) == 1


async def test_cooldown_can_be_disabled(env: tuple) -> None:
    client, s = env
    _set_cooldown(0)
    await _make_user(s, "sl6", _ALL)
    await _login(client, "sl6")
    eid = await _archived(client)

    for ver in (5, 7):
        r = await client.post(
            f"/api/v1/events/{eid}/reactivate",
            json={"confirm": True, "reason": "ok", "token": await _intent(client, eid)},
            headers=_cmd(version=ver),
        )
        assert r.status_code == 200, r.text
        if ver == 5:
            await client.post(
                f"/api/v1/events/{eid}/archive", json={"reason": "z"}, headers=_cmd(version=6)
            )
    assert await _reactivated_count(s) == 2


async def test_intent_on_a_non_archived_event_is_409(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl7", _ALL)
    await _login(client, "sl7")
    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = r.json()["id"]
    assert (await client.post(f"/api/v1/events/{eid}/reactivation-intent")).status_code == 409


async def test_intent_requires_reactivate_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl8", ["events.create", "events.view"])
    await _login(client, "sl8")
    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = r.json()["id"]
    assert (await client.post(f"/api/v1/events/{eid}/reactivation-intent")).status_code == 403


async def _reactivated_count(s: AsyncSession) -> int:
    return (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EVENT_REACTIVATED")
        )
    ).scalar_one()
