"""Runtime secret access (roadmap E23-01, ADR-0019).

Secrets are read through a :class:`SecretProvider`. Today the default is
:class:`EnvFileSecretProvider` — the ADR-0015 mechanism (a
``$BBZ_SECRETS_DIR/<name>`` file, else the ``BBZ_<NAME>`` env var) — short-TTL
cached so a **rotated mounted secret is picked up without a restart**. The
target store is HashiCorp Vault; :class:`VaultSecretProvider` is the seam and is
not wired to a live Vault yet (its rollout is a later issue).

- :func:`verify_required_secrets` runs at startup and refuses to boot when a
  secret the running configuration needs is missing or still the dev
  placeholder.
- :class:`bbz_core.infra.repositories.secrets_rotation.SecretsRotationService`
  re-reads the tracked secrets and audits ``SECRET_ROTATED`` (name only).

``Settings`` keeps its own (identical) ``pydantic-settings`` env/file loading for
now; routing it through the provider lands with the Vault rollout.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from bbz_core.settings import Settings

#: settings fields (without the ``BBZ_`` prefix) that hold a secret value —
#: what the rotation service tracks and what a future Vault source would map.
SECRET_FIELDS: tuple[str, ...] = (
    "jwt_secret",
    "totp_encryption_key",
    "door_dtmf_encryption_key",
    "ldap_bind_password",
    "oidc_entra_client_secret",
)

#: the known-insecure default of ``Settings.jwt_secret``
DEV_JWT_DEFAULT = "dev-insecure-secret-change-me-min-32-bytes!!"


class MissingSecretError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"required secret {name!r} is not available from the secret provider")
        self.name = name


class SecretsIncompleteError(RuntimeError):
    """Raised at startup — the process must not run with these unmet."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("required secrets missing / insecure:\n  - " + "\n  - ".join(problems))
        self.problems = problems


class SecretProvider(Protocol):
    def get(self, name: str) -> str | None: ...
    def version(self, name: str) -> str | None: ...
    def invalidate(self) -> None: ...


class EnvFileSecretProvider:
    """``BBZ_<NAME>`` env, else ``$BBZ_SECRETS_DIR/<name>`` file. Values are
    cached for ``ttl`` seconds so a rotated file is seen without a restart."""

    def __init__(self, secrets_dir: str | None = None, *, ttl: float = 30.0) -> None:
        self._dir = Path(secrets_dir) if secrets_dir else None
        self._ttl = ttl
        self._cache: dict[str, tuple[float, str | None]] = {}

    def _read(self, name: str) -> str | None:
        env = os.environ.get(name.upper())
        if env is not None:
            return env
        if self._dir is not None:
            f = self._dir / name.lower()
            if f.is_file():
                return f.read_text(encoding="utf-8").strip()
        return None

    def get(self, name: str) -> str | None:
        now = time.monotonic()
        hit = self._cache.get(name)
        if hit is not None and now - hit[0] < self._ttl:
            return hit[1]
        val = self._read(name)
        self._cache[name] = (now, val)
        return val

    def version(self, name: str) -> str | None:
        if os.environ.get(name.upper()) is not None:
            return "env"
        if self._dir is not None:
            f = self._dir / name.lower()
            if f.is_file():
                return f"mtime:{f.stat().st_mtime_ns}"
        return None

    def invalidate(self) -> None:
        self._cache.clear()


class VaultSecretProvider:
    """AppRole + KV v2 — the ADR-0019 target. Not wired to a live Vault yet."""

    def __init__(self) -> None:
        raise NotImplementedError(
            "the Vault secret provider is not wired yet — see ADR-0019 "
            "(its rollout is a later issue). Leave BBZ_SECRET_PROVIDER=env."
        )

    def get(self, name: str) -> str | None:  # pragma: no cover
        raise NotImplementedError

    def version(self, name: str) -> str | None:  # pragma: no cover
        raise NotImplementedError

    def invalidate(self) -> None:  # pragma: no cover
        raise NotImplementedError


@lru_cache
def get_secret_provider() -> SecretProvider:
    if os.environ.get("BBZ_SECRET_PROVIDER", "env").lower() == "vault":
        return VaultSecretProvider()
    return EnvFileSecretProvider(os.environ.get("BBZ_SECRETS_DIR") or None)


def resolve_secret(name: str, *, required: bool = False, default: str | None = None) -> str | None:
    """Read secret ``name`` (e.g. ``"bbz_jwt_secret"``). ``required`` + missing
    (or empty) raises :class:`MissingSecretError`."""
    val = get_secret_provider().get(name)
    if not val:
        if required:
            raise MissingSecretError(name)
        return default
    return val


def _dsn_password_missing(dsn: str) -> bool:
    if "@" not in dsn or "://" not in dsn:
        return False
    creds = dsn.split("://", 1)[1].split("@", 1)[0]
    return ":" not in creds or creds.split(":", 1)[1] == ""


def verify_required_secrets(settings: Settings) -> None:
    """Fail-closed startup check (E23-01). No-op outside staging/production."""
    if settings.environment not in ("staging", "production"):
        return
    problems: list[str] = []
    if settings.jwt_secret in ("", DEV_JWT_DEFAULT):
        problems.append("jwt_secret is unset or still the insecure dev default")
    if _dsn_password_missing(settings.database_url):
        problems.append("database_url has no password")
    if problems:
        raise SecretsIncompleteError(problems)
