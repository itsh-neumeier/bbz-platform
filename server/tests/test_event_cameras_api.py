"""Operator-facing per-event camera view (roadmap E16-12 / #357, ADR-0032).

``GET /events/{id}/cameras`` projects the event's CAMERA_OPENED / CAMERA_ACTION_FAILED
domain-event trail and enriches it with a live ``video.resolve_camera`` status,
degrading to ``provider_available: false`` when the integration is down.
``POST /events/{id}/cameras/{ref}/focus`` enqueues one decoupled outbox row for
the operator's workplace, idempotent + audited.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.events import EventAggregate, EventPriority
from bbz_core.infra.event_log import append_event
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.repositories.events import EventRepository
from bbz_core.integrations_host import cameras as cameras_host
from bbz_core.integrations_host.providers import NoActiveProvider


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "evt-cams-test-secret-at-least-32-bytes-ok!!"
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
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def _make_event(s: AsyncSession, actor: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    agg = EventAggregate.create(
        event_id=eid,
        title="Überfall SP",
        priority=EventPriority.CRITICAL,
        actor_id=actor,
        source="trigger",
    )
    async with s.begin():
        await EventRepository(s).add(agg, actor_id=actor)
    return eid


async def _note(s: AsyncSession, event_id: uuid.UUID, event_type: str, refs: list[str]) -> None:
    async with s.begin():
        await append_event(
            s,
            aggregate_type="event",
            aggregate_id=event_id,
            event_type=event_type,
            payload={"action_type": "open_camera_group", "camera_refs": refs},
        )


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


class _FakeCam:
    def __init__(self, camera_id: str, online: bool) -> None:
        self.camera_id = camera_id
        self.name = f"Kamera {camera_id}"
        self.site = "SP Nürnberg"
        self.online = online
        self.group_ids = ["grp-1"]


class _FakeVideoProvider:
    def __init__(self, online: dict[str, bool]) -> None:
        self._online = online

    async def resolve_camera(self, *, external_id: str) -> _FakeCam:
        from bbz_integration_sdk.providers.video_types import CameraNotFoundError

        if external_id not in self._online:
            raise CameraNotFoundError(external_id)
        return _FakeCam(external_id, self._online[external_id])


# --- GET /events/{id}/cameras -------------------------------------------------


async def test_lists_the_events_cameras_with_live_status(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1", "CAM-2"])
    await _note(s, event_id, "CAMERA_ACTION_FAILED", ["CAM-2"])  # CAM-2 later failed

    async def _provider() -> Any:
        return _FakeVideoProvider({"CAM-1": True, "CAM-2": False})

    monkeypatch.setattr(cameras_host, "active_video_provider", _provider)
    await _login(client, "op")

    r = await client.get(f"/api/v1/events/{event_id}/cameras")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_available"] is True
    by_ref = {c["ref"]: c for c in body["cameras"]}
    assert by_ref["CAM-1"]["online"] is True
    assert by_ref["CAM-1"]["last_action_state"] == "opened"
    assert by_ref["CAM-2"]["online"] is False
    assert by_ref["CAM-2"]["last_action_state"] == "failed"  # newest action wins


async def test_degrades_when_no_video_integration_is_active(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-9"])

    async def _down() -> Any:
        raise NoActiveProvider("no video integration")

    monkeypatch.setattr(cameras_host, "active_video_provider", _down)
    await _login(client, "op")

    body = (await client.get(f"/api/v1/events/{event_id}/cameras")).json()
    assert body["provider_available"] is False
    assert body["cameras"][0]["ref"] == "CAM-9"
    assert body["cameras"][0]["online"] is None


async def test_an_unresolvable_camera_is_listed_with_null_status(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1", "GHOST"])

    async def _provider() -> Any:
        return _FakeVideoProvider({"CAM-1": True})  # GHOST does not resolve

    monkeypatch.setattr(cameras_host, "active_video_provider", _provider)
    await _login(client, "op")

    body = (await client.get(f"/api/v1/events/{event_id}/cameras")).json()
    assert body["provider_available"] is True
    by_ref = {c["ref"]: c for c in body["cameras"]}
    assert by_ref["CAM-1"]["online"] is True
    assert by_ref["GHOST"]["online"] is None


async def test_no_camera_trail_returns_an_empty_list(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _login(client, "op")

    body = (await client.get(f"/api/v1/events/{event_id}/cameras")).json()
    assert body == {"provider_available": True, "cameras": []}


async def test_cameras_needs_integrations_view(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view"])  # no integrations.view
    event_id = await _make_event(s, actor)
    await _login(client, "op")
    assert (await client.get(f"/api/v1/events/{event_id}/cameras")).status_code == 403


async def test_cameras_404_for_an_unknown_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["integrations.view"])
    await _login(client, "op")
    assert (await client.get(f"/api/v1/events/{uuid.uuid4()}/cameras")).status_code == 404


# --- POST /events/{id}/cameras/{ref}/focus ----------------------------------


def _cmd(workplace: str | None = "wp-op-1") -> dict[str, str]:
    h = {"X-Command-Id": str(uuid.uuid4())}
    if workplace is not None:
        h["X-Workplace-Id"] = workplace
    return h


async def test_focus_enqueues_one_outbox_row_for_the_operator_workplace(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1"])
    await _login(client, "op")

    r = await client.post(f"/api/v1/events/{event_id}/cameras/CAM-1/focus", headers=_cmd("wp-op-1"))
    assert r.status_code == 200, r.text
    assert r.json() == {"enqueued": True, "camera_ref": "CAM-1", "workplace_id": "wp-op-1"}

    await s.rollback()
    row = (
        await s.execute(
            select(ExternalActionOutbox).where(ExternalActionOutbox.action_type == "open_camera")
        )
    ).scalar_one()
    assert row.payload["camera_ref"] == "CAM-1"
    assert row.payload["workplace_id"] == "wp-op-1"
    assert row.payload["event_id"] == str(event_id)
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "CAMERA_FOCUS_REQUESTED")
        )
    ).scalar_one() == 1


async def test_focus_is_idempotent_on_the_command_id(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1"])
    await _login(client, "op")

    headers = _cmd("wp-op-1")
    first = await client.post(f"/api/v1/events/{event_id}/cameras/CAM-1/focus", headers=headers)
    second = await client.post(f"/api/v1/events/{event_id}/cameras/CAM-1/focus", headers=headers)
    assert first.json()["enqueued"] is True
    assert second.json()["enqueued"] is False

    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(ExternalActionOutbox)
            .where(ExternalActionOutbox.action_type == "open_camera")
        )
    ).scalar_one() == 1
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "CAMERA_FOCUS_REQUESTED")
        )
    ).scalar_one() == 1  # audited once, not twice


async def test_focus_requires_a_workplace_header(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1"])
    await _login(client, "op")

    r = await client.post(f"/api/v1/events/{event_id}/cameras/CAM-1/focus", headers=_cmd(None))
    assert r.status_code == 422


async def test_focus_rejects_a_camera_not_on_the_event(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view", "integrations.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1"])
    await _login(client, "op")

    r = await client.post(
        f"/api/v1/events/{event_id}/cameras/CAM-99/focus", headers=_cmd("wp-op-1")
    )
    assert r.status_code == 404


async def test_focus_needs_integrations_view(env: tuple) -> None:
    client, s = env
    actor = await _make_user(s, "op", ["events.view"])
    event_id = await _make_event(s, actor)
    await _note(s, event_id, "CAMERA_OPENED", ["CAM-1"])
    await _login(client, "op")

    r = await client.post(f"/api/v1/events/{event_id}/cameras/CAM-1/focus", headers=_cmd("wp-op-1"))
    assert r.status_code == 403
