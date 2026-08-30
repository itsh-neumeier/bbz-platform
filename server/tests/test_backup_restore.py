"""Backup/restore scaffold: scripts, gpg round-trip, audit marker (E06-14)."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent

_ROOT = Path(__file__).resolve().parents[2]
_BACKUP = _ROOT / "deploy" / "backup"
_SCRIPTS = ["common.sh", "pg-backup.sh", "pg-restore.sh", "etcd-backup.sh", "etcd-restore.sh"]


@pytest.mark.parametrize("name", _SCRIPTS)
def test_scripts_are_valid_posix_shell(name: str) -> None:
    assert subprocess.run(["sh", "-n", str(_BACKUP / name)]).returncode == 0


def test_systemd_units_and_runbook_exist() -> None:
    units = sorted(p.name for p in (_BACKUP / "systemd").glob("*"))
    assert units == [
        "bbz-etcd-backup.service",
        "bbz-etcd-backup.timer",
        "bbz-pg-backup.service",
        "bbz-pg-backup.timer",
    ]
    rb = (_ROOT / "docs" / "runbooks" / "restore.md").read_text(encoding="utf-8")
    assert "PostgreSQL" in rb and "etcd" in rb and "RPO" in rb


def test_backups_are_encrypted_and_the_key_is_offline() -> None:
    common = (_BACKUP / "common.sh").read_text(encoding="utf-8")
    assert "gpg" in common and "--encrypt" in common
    readme = (_BACKUP / "README.md").read_text(encoding="utf-8")
    assert "offline" in readme.lower() and "asymmetric" in readme.lower()


@pytest.mark.skipif(not (shutil.which("gpg") and shutil.which("sh")), reason="needs gpg + sh")
def test_gpg_encrypt_decrypt_round_trip(tmp_path: Path) -> None:
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    env = {
        **os.environ,
        "GNUPGHOME": str(home),
        "GPG_RECIPIENT": "ci-backup",
        "BACKUP_DIR": str(tmp_path),
    }
    gen = subprocess.run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-generate-key",
            "ci-backup",
            "default",
            "default",
            "none",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if gen.returncode != 0:
        pytest.skip(f"gpg key generation unavailable here: {gen.stderr.strip()[:120]}")
    script = (
        f'. "{_BACKUP / "common.sh"}"; '
        f'printf "top secret audit rows" | gpg_encrypt "{tmp_path / "b.gpg"}"; '
        f'gpg_decrypt "{tmp_path / "b.gpg"}"'
    )
    out = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "top secret audit rows"


# --- the audit marker endpoint ------------------------------------------


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "backup-test-secret-at-least-32-bytes-okok!"
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


async def test_backup_marker_audits_and_needs_cluster_manage(env: tuple) -> None:
    client, s = env
    assert (
        await client.post("/api/v1/system/backup", json={"phase": "completed", "kind": "postgres"})
    ).status_code == 401

    await _make_user(s, "op", ["system.cluster.manage"])
    await _login(client, "op")
    assert (
        await client.post(
            "/api/v1/system/backup",
            json={"phase": "restored", "kind": "etcd", "notes": "DR drill"},
        )
    ).status_code == 202

    row = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "RESTORE_PERFORMED"))
    ).scalar_one()
    assert row.target_type == "backup:etcd" and row.reason == "DR drill"
