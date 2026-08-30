"""GET /calls — call history: filters, permissions, pagination (E11-11)."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.telephony import Call, CallDocumentation, CallParticipant


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "call-history-secret-at-least-32-bytes-ok!!"
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


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _at(day: int) -> _dt.datetime:
    return _dt.datetime(2026, 8, 1, 9, 0, tzinfo=_dt.UTC) + _dt.timedelta(days=day)


async def _add_call(
    s: AsyncSession,
    *,
    tag: str,
    direction: str,
    state: str,
    day: int,
    number: str | None = None,
    role: str = "caller",
    category: str | None = None,
    free_text: str | None = None,
) -> uuid.UUID:
    call = Call(
        bbz_call_id=f"CALL-{tag}",
        provider="telephony_mock",
        source_call_id=f"s-{tag}",
        direction=direction,
        state=state,
        created_at=_at(day),
        started_at=_at(day),
    )
    s.add(call)
    await s.flush()
    if number is not None:
        s.add(CallParticipant(call_id=call.id, number=number, display_name="Leitstelle", role=role))
    if category is not None or free_text is not None:
        s.add(
            CallDocumentation(
                call_id=call.id,
                category=category,
                free_text=free_text,
                mandatory_done=category is not None,
            )
        )
    return call.id


@pytest.fixture
async def seeded(client: httpx.AsyncClient, db: object) -> AsyncIterator[httpx.AsyncClient]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", ["calls.view_history"])
    await _make_user(s, "weak", ["calls.view"])
    await _login(client, "op")

    # created oldest -> newest: a, b, c, d, e  => history returns e, d, c, b, a
    await _add_call(s, tag="a", direction="inbound", state="disconnected", day=0, number="+49111")
    await _add_call(
        s,
        tag="b",
        direction="outbound",
        state="disconnected",
        day=1,
        number="+49222",
        role="callee",
        category="technical_fault",
        free_text="Weiche klemmt",
    )
    await _add_call(
        s, tag="c", direction="inbound", state="ended_pending_documentation", day=2, number="+49111"
    )
    await _add_call(
        s,
        tag="d",
        direction="inbound",
        state="disconnected",
        day=3,
        number="+49333",
        category="information_request",
    )
    await _add_call(s, tag="e", direction="outbound", state="failed", day=4)
    await s.commit()
    yield client


def _tags(body: dict) -> list[str]:
    return [it["bbz_call_id"].removeprefix("CALL-") for it in body["items"]]


async def test_history_requires_view_history_permission(seeded: httpx.AsyncClient) -> None:
    await _login(seeded, "weak")
    r = await seeded.get("/api/v1/calls")
    assert r.status_code == 403


async def test_history_returns_all_calls_newest_first(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls")
    assert r.status_code == 200
    assert _tags(r.json()) == ["e", "d", "c", "b", "a"]
    assert r.json()["next_cursor"] is None


async def test_filter_by_direction(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls", params={"direction": "outbound"})
    assert _tags(r.json()) == ["e", "b"]


async def test_filter_by_state(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls", params={"state": "failed"})
    assert _tags(r.json()) == ["e"]


async def test_filter_by_number_matches_any_participant(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls", params={"number": "+49111"})
    assert _tags(r.json()) == ["c", "a"]


async def test_filter_by_category(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls", params={"category": "technical_fault"})
    assert _tags(r.json()) == ["b"]


async def test_filter_by_time_range_is_inclusive_on_created_at(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get(
        "/api/v1/calls",
        params={"since": _at(1).isoformat(), "until": _at(3).isoformat()},
    )
    assert _tags(r.json()) == ["d", "c", "b"]


async def test_unknown_filter_value_is_422(seeded: httpx.AsyncClient) -> None:
    assert (await seeded.get("/api/v1/calls", params={"direction": "sideways"})).status_code == 422
    assert (await seeded.get("/api/v1/calls", params={"category": "smalltalk"})).status_code == 422


async def test_keyset_pagination_walks_the_whole_history_once(seeded: httpx.AsyncClient) -> None:
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, str] = {"limit": "2"}
        if cursor is not None:
            params["cursor"] = cursor
        body = (await seeded.get("/api/v1/calls", params=params)).json()
        seen.extend(_tags(body))
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
        assert pages < 10  # guard against a cursor that never terminates
    assert seen == ["e", "d", "c", "b", "a"]
    assert pages == 3


async def test_payload_carries_participants_and_documentation_flags(
    seeded: httpx.AsyncClient,
) -> None:
    body = (await seeded.get("/api/v1/calls", params={"number": "+49222"})).json()
    (item,) = body["items"]
    assert item["direction"] == "outbound"
    assert item["category"] == "technical_fault"
    assert item["has_free_text"] is True
    assert item["participants"] == [
        {"number": "+49222", "display_name": "Leitstelle", "role": "callee"}
    ]


async def test_call_without_documentation_reports_null_category(seeded: httpx.AsyncClient) -> None:
    body = (await seeded.get("/api/v1/calls", params={"state": "failed"})).json()
    (item,) = body["items"]
    assert item["category"] is None
    assert item["has_free_text"] is False
    assert item["participants"] == []


async def test_a_malformed_cursor_is_rejected(seeded: httpx.AsyncClient) -> None:
    r = await seeded.get("/api/v1/calls", params={"cursor": "not-a-real-cursor"})
    assert r.status_code == 422


async def test_history_has_no_side_effects_on_the_audit_log(seeded: httpx.AsyncClient) -> None:
    from bbz_core.infra.models.audit import AuditEvent

    await seeded.get("/api/v1/calls")

    from bbz_core.infra.db import get_sessionmaker

    async with get_sessionmaker()() as s:
        n = (
            (await s.execute(select(AuditEvent).where(AuditEvent.action.like("CALL%"))))
            .scalars()
            .all()
        )
    assert n == []
