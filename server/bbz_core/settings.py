"""Application settings.

All configuration comes from the environment (12-factor). Secrets are never
committed; ``.env.example`` documents the shape only. See ADR-0015.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BBZ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- identity / deployment ---
    environment: Literal["local", "ci", "staging", "production"] = "local"
    node_id: str = Field(
        default="BBZ-LOCAL",
        description="Logical node identity (e.g. BBZ-SRV01). Written into events/audit later.",
    )
    service_name: str = "bbz-api"
    log_level: str = "INFO"
    log_json: bool = True

    # --- HTTP ---
    api_root_path: str = ""
    cors_allow_origins: list[str] = Field(default_factory=list)

    # --- database ---
    database_url: str = Field(
        default="postgresql+asyncpg://bbz:bbz@localhost:5432/bbz",
        description="SQLAlchemy async DSN. Overridden per deployment.",
    )
    database_pool_size: int = 5

    # --- cluster / HA (Phase 2 wires these; Phase 0 only reports them) ---
    cluster_dcs: Literal["etcd", "consul"] = "etcd"
    cluster_dcs_endpoints: list[str] = Field(default_factory=lambda: ["http://localhost:2379"])

    # --- auth: providers (E02-04). 'local' is always active regardless. ---
    auth_providers: list[str] = Field(default_factory=lambda: ["local"])

    # --- authorization (E02-07). Conditional grants stay deny until E05-01. ---
    rbac_conditions_enabled: bool = False

    # --- MFA / TOTP (E02-13). Fernet key (urlsafe-base64, 32 bytes) for the
    # secret at rest; empty in dev disables enrolment. Real secret store: ADR-0019.
    totp_encryption_key: str = ""
    totp_issuer: str = "BBZ / 3-S-Zentrale"

    # --- auth: sessions / tokens (E02-05; secret via ADR-0015 in prod) ---
    jwt_secret: str = "dev-insecure-secret-change-me-min-32-bytes!!"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = True
    session_cookie_domain: str | None = None

    # --- auth: local password credentials (ADR-0015; E02-03) ---
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4
    password_min_length: int = 12
    password_min_char_classes: int = 3  # of {lower, upper, digit, symbol}
    login_max_failed_attempts: int = 5
    login_lockout_seconds: int = 900

    @property
    def database_url_sync(self) -> str:
        """Sync DSN for Alembic (psycopg v3 driver)."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
