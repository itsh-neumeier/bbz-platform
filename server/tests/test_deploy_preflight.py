"""E24-03: deploy/node/preflight.sh aborts on a half-provisioned environment."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "deploy" / "node" / "preflight.sh"

_GOOD_ENV = """\
BBZ_NODE_ID=BBZ-SRV01
BBZ_ENVIRONMENT=staging
BBZ_PUBLIC_NAME=bbz.staging.internal
BBZ_API_IMAGE=ghcr.io/x/bbz-api@sha256:aaaa
BBZ_WEB_IMAGE=ghcr.io/x/bbz-web@sha256:bbbb
BBZ_DATABASE_URL=postgresql+asyncpg://bbz:s3cret@bbz-srv01:5432/bbz
BBZ_CLUSTER_DCS_ENDPOINTS=["https://bbz-srv01:2379"]
"""

_SECRETS = {
    "bbz_jwt_secret": "x" * 48,
    "bbz_totp_encryption_key": "y" * 44,
    "postgres_superuser_password": "pg-super-pw",
    "postgres_replication_password": "pg-repl-pw",
}


def _node(tmp_path: Path, *, env: str = _GOOD_ENV, secrets: dict[str, str] | None = None) -> Path:
    (tmp_path / ".env").write_text(env, encoding="utf-8")
    sd = tmp_path / "secrets"
    sd.mkdir()
    for name, value in (secrets if secrets is not None else _SECRETS).items():
        (sd / name).write_text(value, encoding="utf-8")
    certs = tmp_path / "etcd" / "certs"
    certs.mkdir(parents=True)
    for c in ("ca.crt", "client-bbz-app.crt", "client-bbz-app.key"):
        (certs / c).write_text("pem", encoding="utf-8")
    return tmp_path


def _run(node: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(_SCRIPT), str(node)], capture_output=True, text=True, timeout=30
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX sh required")
class TestPreflight:
    def test_a_fully_provisioned_node_passes(self, tmp_path: Path) -> None:
        r = _run(_node(tmp_path))
        assert r.returncode == 0, r.stderr
        assert "pre-flight OK" in r.stdout

    def test_a_missing_env_file_aborts(self, tmp_path: Path) -> None:
        (tmp_path / "secrets").mkdir()
        r = _run(tmp_path)
        assert r.returncode == 1
        assert ".env is missing" in r.stderr

    def test_a_placeholder_secret_aborts(self, tmp_path: Path) -> None:
        node = _node(tmp_path, secrets={**_SECRETS, "bbz_jwt_secret": "CHANGE_ME_please"})
        r = _run(node)
        assert r.returncode == 1
        assert "bbz_jwt_secret is still the placeholder" in r.stderr

    def test_a_missing_secret_file_aborts(self, tmp_path: Path) -> None:
        secrets = {k: v for k, v in _SECRETS.items() if k != "bbz_totp_encryption_key"}
        r = _run(_node(tmp_path, secrets=secrets))
        assert r.returncode == 1
        assert "secrets/bbz_totp_encryption_key is missing" in r.stderr

    def test_a_passwordless_dsn_aborts(self, tmp_path: Path) -> None:
        env = _GOOD_ENV.replace("bbz:s3cret@", "bbz@")
        r = _run(_node(tmp_path, env=env))
        assert r.returncode == 1
        assert "no password" in r.stderr

    def test_a_short_jwt_secret_aborts(self, tmp_path: Path) -> None:
        r = _run(_node(tmp_path, secrets={**_SECRETS, "bbz_jwt_secret": "tooshort"}))
        assert r.returncode == 1
        assert "shorter than 32 bytes" in r.stderr

    def test_production_rejects_a_latest_image(self, tmp_path: Path) -> None:
        env = _GOOD_ENV.replace("BBZ_ENVIRONMENT=staging", "BBZ_ENVIRONMENT=production").replace(
            "bbz-api@sha256:aaaa", "bbz-api:latest"
        )
        r = _run(_node(tmp_path, env=env))
        assert r.returncode == 1
        assert "pin a digest in production" in r.stderr

    def test_missing_etcd_certs_abort(self, tmp_path: Path) -> None:
        node = _node(tmp_path)
        (node / "etcd" / "certs" / "ca.crt").unlink()
        r = _run(node)
        assert r.returncode == 1
        assert "etcd/certs/ca.crt is missing" in r.stderr
