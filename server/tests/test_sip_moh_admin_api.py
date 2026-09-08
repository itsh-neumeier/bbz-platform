"""SIP music-on-hold admin API (E13-12 / #817): raw-body WAV upload, list,
delete (409 while a line uses it), download, the plain-text sync manifest, and
the per-line assignment on ``PUT /admin/telephony/sip/lines/{id}``. Every route
needs ``integrations.configure``."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent


def _wav(payload: bytes = b"\x00" * 32) -> bytes:
    body = (
        b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (8000).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (8).to_bytes(2, "little")
        + b"data"
        + len(payload).to_bytes(4, "little")
        + payload
    )
    return b"RIFF" + (len(body)).to_bytes(4, "little") + body


@pytest.fixture(autouse=True)
def _env(tmp_path: Path) -> Iterator[None]:
    import bbz_core.settings as settings_mod
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "sip-moh-test-secret-at-least-32-bytes-ok!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_MOH_DIR"] = str(tmp_path / "moh")
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    settings_mod.get_settings.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    os.environ.pop("BBZ_MOH_DIR", None)
    settings_mod.get_settings.cache_clear()


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
    assert isinstance(db, AsyncSession)
    yield client, db


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def _upload(client: httpx.AsyncClient, name: str, data: bytes) -> dict:
    r = await client.post(
        f"/api/v1/admin/telephony/moh?name={name}&filename={name}.wav",
        content=data,
        headers={"Content-Type": "audio/wav"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_routes_need_integrations_configure(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/admin/telephony/moh")).status_code == 401
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/admin/telephony/moh")).status_code == 403


async def test_upload_list_download_roundtrip(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")

    body = _wav(b"\x11" * 100)
    up = await _upload(client, "Bahnhofsmusik", body)
    assert up["name"] == "Bahnhofsmusik" and up["size_bytes"] == len(body)
    assert up["used_by"] == []

    listed = (await client.get("/api/v1/admin/telephony/moh")).json()
    assert [f["id"] for f in listed["files"]] == [up["id"]]

    dl = await client.get(f"/api/v1/admin/telephony/moh/{up['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "audio/wav"
    assert dl.content == body

    rows = (await s.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_MOH_UPLOADED" for r in rows)


async def test_a_non_wav_upload_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.post(
        "/api/v1/admin/telephony/moh?name=x",
        content=b"this is not audio",
        headers={"Content-Type": "audio/wav"},
    )
    assert r.status_code == 422


async def test_assign_to_a_line_then_delete_is_409_until_reassigned(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    up = await _upload(client, "Halten", _wav())

    # assign it as the hold music of a line
    r = await client.put(
        "/api/v1/admin/telephony/sip/lines/leonet-8870",
        json={"label": "MSN 8870", "enabled": True, "hold_moh_file_id": up["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["hold_moh_file_id"] == up["id"]

    # the file now shows the line, and cannot be deleted
    listed = (await client.get("/api/v1/admin/telephony/moh")).json()["files"][0]
    assert listed["used_by"] == ["leonet-8870"]
    assert (await client.delete(f"/api/v1/admin/telephony/moh/{up['id']}")).status_code == 409

    # clear the assignment, then it deletes
    await client.put(
        "/api/v1/admin/telephony/sip/lines/leonet-8870",
        json={"label": "MSN 8870", "enabled": True, "hold_moh_file_id": None},
    )
    assert (await client.delete(f"/api/v1/admin/telephony/moh/{up['id']}")).status_code == 204
    assert (await client.get("/api/v1/admin/telephony/moh")).json()["files"] == []


async def test_manifest_and_musiconhold_config(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    ring = await _upload(client, "Warte", _wav())
    hold = await _upload(client, "Halte", _wav(b"\x33"))
    await client.put(
        "/api/v1/admin/telephony/sip/lines/leonet-8870",
        json={
            "label": "",
            "enabled": True,
            "ring_moh_file_id": ring["id"],
            "hold_moh_file_id": hold["id"],
        },
    )

    manifest = await client.get("/api/v1/admin/telephony/moh/manifest")
    assert manifest.headers["content-type"].startswith("text/plain")
    ids = {line.split()[0] for line in manifest.text.splitlines() if line.strip()}
    assert ids == {ring["id"], hold["id"]}

    conf = await client.get("/api/v1/admin/telephony/sip/asterisk-config?part=musiconhold")
    assert conf.status_code == 200
    assert f"[bbz-moh-{ring['id']}]" in conf.text
    assert conf.headers["cache-control"] == "no-store"


async def test_unknown_moh_id_on_a_line_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.put(
        "/api/v1/admin/telephony/sip/lines/l1",
        json={"label": "", "enabled": True, "ring_moh_file_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422
