"""GET /events archive-view filters — date / priority / bbz / responsible (E20-02).

Extends the E03-12 chronological list. Archived events are visible here but never
in ``queue=active``; pagination stays stable when a filter is applied.
"""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.events import Event, EventAssignment

_PERMS = ["events.create", "events.view"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "archive-list-secret-at-least-32-bytes-okay!!"
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


def _at(day: int) -> _dt.datetime:
    return _dt.datetime(2026, 3, day, 12, 0, tzinfo=_dt.UTC)


async def _seed(s: AsyncSession) -> dict[str, uuid.UUID]:
    """4 events on 2026-03-10..13, across priorities, one shared bbz, 2 archived."""
    bbz = uuid.uuid4()
    rows = {
        "low_10": Event(title="low_10", priority="low", status="archived", created_at=_at(10)),
        "high_11": Event(
            title="high_11", priority="high", status="archived", bbz_id=bbz, created_at=_at(11)
        ),
        "crit_12": Event(title="crit_12", priority="critical", status="opened", created_at=_at(12)),
        "med_13": Event(
            title="med_13", priority="medium", status="new", bbz_id=bbz, created_at=_at(13)
        ),
    }
    for r in rows.values():
        s.add(r)
    await s.flush()
    ids = {name: r.id for name, r in rows.items()}
    await s.commit()
    return {**ids, "bbz": bbz}


async def _titles(client: httpx.AsyncClient, query: str) -> list[str]:
    r = await client.get(f"/api/v1/events{query}")
    assert r.status_code == 200, r.text
    return [i["title"] for i in r.json()["items"]]


async def test_priority_filter_is_an_or_set(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _PERMS)
    await _login(client, "op")
    await _seed(s)
    assert await _titles(client, "?priority=high&priority=critical") == ["crit_12", "high_11"]
    assert await _titles(client, "?priority=low") == ["low_10"]


async def test_date_range_filter(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _PERMS)
    await _login(client, "op2")
    await _seed(s)
    got = await _titles(
        client, "?created_from=2026-03-11T00:00:00Z&created_to=2026-03-12T23:59:59Z"
    )
    assert got == ["crit_12", "high_11"]


async def test_bbz_filter(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _PERMS)
    await _login(client, "op3")
    ids = await _seed(s)
    assert await _titles(client, f"?bbz_id={ids['bbz']}") == ["med_13", "high_11"]


async def test_assignee_filter_matches_active_responsible(env: tuple) -> None:
    client, s = env
    uid = await _make_user(s, "op4", _PERMS)
    await _login(client, "op4")
    ids = await _seed(s)
    s.add(EventAssignment(event_id=ids["crit_12"], user_id=uid, active=True))
    s.add(EventAssignment(event_id=ids["low_10"], user_id=uid, active=False))
    await s.commit()
    assert await _titles(client, f"?assignee_id={uid}") == ["crit_12"]


async def test_archived_visible_here_but_not_in_active_queue(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", _PERMS)
    await _login(client, "op5")
    await _seed(s)

    listed = await _titles(client, "?status=archived")
    assert set(listed) == {"low_10", "high_11"}

    active = await _titles(client, "?queue=active")
    assert "low_10" not in active and "high_11" not in active
    assert set(active) == {"crit_12", "med_13"}


async def test_pagination_is_stable_under_a_filter(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op6", _PERMS)
    await _login(client, "op6")
    ids = await _seed(s)

    page1 = (await client.get(f"/api/v1/events?bbz_id={ids['bbz']}&limit=1")).json()
    assert [i["title"] for i in page1["items"]] == ["med_13"]
    assert page1["next_cursor"]

    page2 = (
        await client.get(
            f"/api/v1/events?bbz_id={ids['bbz']}&limit=1&cursor={page1['next_cursor']}"
        )
    ).json()
    assert [i["title"] for i in page2["items"]] == ["high_11"]
    assert page2["next_cursor"] is None


async def test_bad_priority_value_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op7", _PERMS)
    await _login(client, "op7")
    assert (await client.get("/api/v1/events?priority=umbra")).status_code == 422
