"""E23-01 / ADR-0019: the SecretProvider abstraction, fail-closed startup and
the rotation endpoint."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.secrets import (
    DEV_JWT_DEFAULT,
    EnvFileSecretProvider,
    SecretsIncompleteError,
    verify_required_secrets,
)

# --- provider -------------------------------------------------------------


def test_env_wins_over_file_and_the_ttl_cache_can_be_invalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bbz_jwt_secret").write_text("from-file", encoding="utf-8")
    p = EnvFileSecretProvider(str(tmp_path), ttl=1000)

    monkeypatch.setenv("BBZ_JWT_SECRET", "from-env")
    assert p.get("bbz_jwt_secret") == "from-env"

    monkeypatch.delenv("BBZ_JWT_SECRET")
    assert p.get("bbz_jwt_secret") == "from-env"  # still cached
    p.invalidate()
    assert p.get("bbz_jwt_secret") == "from-file"

    (tmp_path / "bbz_jwt_secret").write_text("rotated", encoding="utf-8")
    assert p.get("bbz_jwt_secret") == "from-file"  # cached again
    p.invalidate()
    assert p.get("bbz_jwt_secret") == "rotated"


def test_missing_secret_is_none_not_an_error() -> None:
    assert EnvFileSecretProvider(None).get("bbz_nope") is None


def test_selecting_vault_before_it_is_wired_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    from bbz_core import secrets as mod

    monkeypatch.setenv("BBZ_SECRET_PROVIDER", "vault")
    mod.get_secret_provider.cache_clear()
    with pytest.raises(NotImplementedError, match="ADR-0019"):
        mod.get_secret_provider()
    mod.get_secret_provider.cache_clear()


# --- fail-closed startup ------------------------------------------------


class _S:
    def __init__(self, **kw: object) -> None:
        self.environment = kw.get("environment", "local")
        self.jwt_secret = kw.get("jwt_secret", "x" * 40)
        self.database_url = kw.get("database_url", "postgresql+asyncpg://u:pw@h:5432/d")


def test_verify_is_a_noop_outside_staging_and_production() -> None:
    verify_required_secrets(_S(environment="ci", jwt_secret=DEV_JWT_DEFAULT))  # no raise


def test_verify_fails_closed_on_a_dev_jwt_in_production() -> None:
    with pytest.raises(SecretsIncompleteError) as exc:
        verify_required_secrets(_S(environment="production", jwt_secret=DEV_JWT_DEFAULT))
    assert "jwt_secret" in str(exc.value)


def test_verify_flags_a_passwordless_dsn() -> None:
    with pytest.raises(SecretsIncompleteError) as exc:
        verify_required_secrets(
            _S(
                environment="staging",
                database_url="postgresql+asyncpg://bbz@bbz-srv01:5432/bbz",
            )
        )
    assert "database_url" in str(exc.value)


def test_verify_passes_with_real_secrets() -> None:
    verify_required_secrets(
        _S(environment="production", jwt_secret="a-real-secret-value-32-bytes-plus")
    )


# --- rotation endpoint -------------------------------------------------


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "secret-store-test-jwt-at-least-32-bytes!!"
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
    pw = hash_password("Wolke7-Bahnhof!x")
    s.add(LocalCredential(auth_identity_id=ident.id, password_hash=pw))
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


async def _login(c: httpx.AsyncClient, username: str) -> None:
    r = await c.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


async def test_reload_requires_cluster_manage(env: tuple) -> None:
    client, s = env
    assert (await client.post("/api/v1/system/secrets/reload")).status_code == 401
    await _make_user(s, "viewer", ["system.cluster.view"])
    await _login(client, "viewer")
    assert (await client.post("/api/v1/system/secrets/reload")).status_code == 403


async def test_a_rotated_file_secret_is_reloaded_and_audited(
    env: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    from bbz_core import secrets as secrets_mod
    from bbz_core.infra.models.audit import AuditEvent
    from bbz_core.settings import Settings, get_settings

    # a file-sourced door key; no BBZ_DOOR_DTMF_ENCRYPTION_KEY env
    monkeypatch.delenv("BBZ_DOOR_DTMF_ENCRYPTION_KEY", raising=False)
    (tmp_path / "bbz_door_dtmf_encryption_key").write_text("key-v1", encoding="utf-8")
    monkeypatch.setenv("BBZ_SECRETS_DIR", str(tmp_path))
    # model_config.secrets_dir is bound at import; point it at the tmp dir for the test
    monkeypatch.setitem(Settings.model_config, "secrets_dir", str(tmp_path))
    secrets_mod.get_secret_provider.cache_clear()
    get_settings.cache_clear()
    assert get_settings().door_dtmf_encryption_key == "key-v1"

    await _make_user(s, "ops", ["system.cluster.manage"])
    await _login(client, "ops")

    # nothing changed yet
    r = await client.post("/api/v1/system/secrets/reload")
    assert r.status_code == 200 and r.json()["reloaded"] == []

    # rotate the mounted file
    (tmp_path / "bbz_door_dtmf_encryption_key").write_text("key-v2", encoding="utf-8")
    r = await client.post("/api/v1/system/secrets/reload")
    assert r.json()["reloaded"] == ["door_dtmf_encryption_key"]
    assert get_settings().door_dtmf_encryption_key == "key-v2"

    await s.rollback()
    rows = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "SECRET_ROTATED")))
        .scalars()
        .all()
    )
    assert [r.target_id for r in rows] == ["door_dtmf_encryption_key"]
    assert "key-v1" not in str(rows[0].after) and "key-v2" not in str(rows[0].after)

    secrets_mod.get_secret_provider.cache_clear()
    get_settings.cache_clear()
