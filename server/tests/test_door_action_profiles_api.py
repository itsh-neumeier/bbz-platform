"""Door-open DTMF profiles (roadmap E17-02): the code is stored ENCRYPTED and is
never returned by any API, never in an audit row, never in the DB as plaintext
(MASTER_PROMPT §30, .ai/SECURITY.md). Every route needs `door.configure`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.door_action_profiles import DoorActionProfile
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint

_CODE = "12A#"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "door-prof-test-secret-at-least-32-bytes-x!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_DOOR_DTMF_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    os.environ.pop("BBZ_DOOR_DTMF_ENCRYPTION_KEY", None)


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


async def _as_configurer(env: tuple, name: str = "dc") -> None:
    _, s = env
    await _make_user(s, name, ["door.configure"])
    await _login(env[0], name)


def test_door_secrets_round_trip_and_wrong_key() -> None:
    from bbz_core.infra import door_secrets

    ct = door_secrets.encrypt_dtmf(_CODE)
    assert ct != _CODE
    assert door_secrets.decrypt_dtmf(ct) == _CODE

    # a token from another key does not decrypt
    other = Fernet(Fernet.generate_key())
    with pytest.raises(door_secrets.DoorSecretsNotConfigured):
        door_secrets.decrypt_dtmf(other.encrypt(b"x").decode())


async def test_a_profile_stores_the_code_encrypted_and_never_returns_it(env: tuple) -> None:
    client, s = env
    await _as_configurer(env)

    created = await client.post(
        "/api/v1/door-action-profiles",
        json={"name": "Haupttor", "dtmf_code": _CODE, "post_dtmf_delay_ms": 800},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["configured"] is True and body["post_dtmf_delay_ms"] == 800
    # the response never carries the code, nor a dtmf_code / ciphertext field
    assert _CODE not in str(body)
    assert not {"dtmf_code", "dtmf", "code", "dtmf_ciphertext", "ciphertext"} & set(body)

    pid = body["id"]
    detail = await client.get(f"/api/v1/door-action-profiles/{pid}")
    assert _CODE not in detail.text and "ciphertext" not in detail.text
    assert _CODE not in (await client.get("/api/v1/door-action-profiles")).text

    # the DB row holds ciphertext, not the code
    await s.rollback()
    row = (await s.execute(select(DoorActionProfile))).scalar_one()
    assert row.dtmf_ciphertext != _CODE and _CODE not in row.dtmf_ciphertext

    # the service can still recover it for the door-open flow (E17-05)
    from bbz_core.infra.repositories.door_action_profiles import DoorActionProfileService

    code, delay, hangup = await DoorActionProfileService(s).resolve_dtmf(row.id)
    assert code == _CODE and delay == 800 and hangup is True


async def test_no_audit_row_ever_contains_the_code(env: tuple) -> None:
    client, s = env
    await _as_configurer(env)

    pid = (
        await client.post("/api/v1/door-action-profiles", json={"name": "T", "dtmf_code": _CODE})
    ).json()["id"]
    await client.patch(
        f"/api/v1/door-action-profiles/{pid}", json={"dtmf_code": "9999", "name": "T2"}
    )
    await client.delete(f"/api/v1/door-action-profiles/{pid}")

    await s.rollback()
    rows = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action.like("DOOR_PROFILE_%"))))
        .scalars()
        .all()
    )
    assert len(rows) == 3
    for r in rows:
        blob = f"{r.after} {r.before}"
        assert _CODE not in blob and "9999" not in blob and "ciphertext" not in blob
    assert {r.action for r in rows} == {
        "DOOR_PROFILE_CREATED",
        "DOOR_PROFILE_UPDATED",
        "DOOR_PROFILE_DELETED",
    }


async def test_a_raw_code_in_an_unexpected_field_is_rejected(env: tuple) -> None:
    client, s = env
    await _as_configurer(env)
    r = await client.post(
        "/api/v1/door-action-profiles",
        json={"name": "T", "dtmf_code": _CODE, "secret": "1234", "code": "1234"},
    )
    assert r.status_code == 422  # extra="forbid"
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(DoorActionProfile))).scalar_one() == 0


@pytest.mark.parametrize("bad", ["", "12345678901234567890123456789012X", "12 34", "12E4"])
async def test_a_malformed_dtmf_code_is_rejected(env: tuple, bad: str) -> None:
    client, _ = env
    await _as_configurer(env, f"dcx{len(bad)}")
    r = await client.post(
        "/api/v1/door-action-profiles", json={"name": f"T{len(bad)}", "dtmf_code": bad}
    )
    assert r.status_code == 422
    assert _CODE not in r.text  # never echo


async def test_door_configure_is_required(env: tuple) -> None:
    client, s = env
    await _make_user(s, "nope", ["technical_endpoints.manage"])
    await _login(client, "nope")
    for call in (
        client.get("/api/v1/door-action-profiles"),
        client.post("/api/v1/door-action-profiles", json={"name": "T", "dtmf_code": _CODE}),
    ):
        assert (await call).status_code == 403


async def test_deleting_a_profile_nulls_the_endpoint_reference(env: tuple) -> None:
    client, s = env
    await _as_configurer(env)
    pid = (
        await client.post("/api/v1/door-action-profiles", json={"name": "Tor", "dtmf_code": _CODE})
    ).json()["id"]

    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(name="Tür", type="door_station", dtmf_profile_id=uuid.UUID(pid))
        s.add(ep)
        await s.flush()
        eid = ep.id

    assert (await client.delete(f"/api/v1/door-action-profiles/{pid}")).status_code == 204
    await s.rollback()
    ep2 = (
        await s.execute(
            select(TechnicalEndpoint)
            .where(TechnicalEndpoint.id == eid)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert ep2.dtmf_profile_id is None  # ON DELETE SET NULL


async def test_creation_fails_cleanly_when_no_key_is_configured(env: tuple) -> None:
    client, s = env
    os.environ.pop("BBZ_DOOR_DTMF_ENCRYPTION_KEY", None)
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    await _as_configurer(env)

    r = await client.post("/api/v1/door-action-profiles", json={"name": "T", "dtmf_code": _CODE})
    assert r.status_code == 503
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(DoorActionProfile))).scalar_one() == 0


def test_the_table_and_fk_are_registered() -> None:
    md = Base.metadata.tables
    assert "door_action_profiles" in md
    fks = {fk.column.table.name for fk in md["technical_endpoints"].foreign_keys}
    assert "door_action_profiles" in fks
