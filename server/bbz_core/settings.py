"""Application settings.

All configuration comes from the environment (12-factor). Secrets are never
committed; ``.env.example`` documents the shape only. See ADR-0015.
"""

from __future__ import annotations

import os
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
        # Docker/Podman secrets: when BBZ_SECRETS_DIR is set (deploy/node mounts
        # it at /run/secrets), a file named e.g. `bbz_jwt_secret` supplies that
        # field. Unset (dev/CI/tests) -> no secrets source, no warning.
        secrets_dir=os.environ.get("BBZ_SECRETS_DIR") or None,
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
    # etcd mTLS (ADR-0018). Empty -> plain HTTP (dev/tests). In deploy/node the
    # compose points these at the mounted client-bbz-app certificate.
    cluster_dcs_tls_ca_file: str = ""
    cluster_dcs_tls_cert_file: str = ""
    cluster_dcs_tls_key_file: str = ""
    # Patroni REST APIs (one per DB node, e.g. http://bbz-srv01:8008). Empty ->
    # /cluster/status falls back to the local PostgreSQL role only.
    patroni_rest_endpoints: list[str] = Field(default_factory=list)
    # This node's own Patroni REST base (e.g. http://localhost:8008). Empty ->
    # /health/ready skips the cluster check (single-node dev). Set in deploy/node.
    patroni_local_rest_url: str = ""
    # Application leader election (ADR-0018): "" -> local single-node (no etcd),
    # "etcd" -> lease-based election against cluster_dcs_endpoints.
    worker_leader_backend: Literal["", "etcd"] = ""
    worker_leader_ttl_seconds: int = 10
    worker_leader_prefix: str = "/bbz/leader"
    # start the cluster singletons (outbox dispatcher, workflow timer) in the
    # app lifespan. Off by default (tests / bare API); deploy/node sets it.
    run_background_workers: bool = False

    # --- auth: providers (E02-04). 'local' is always active regardless. ---
    auth_providers: list[str] = Field(default_factory=lambda: ["local"])

    # --- authorization (E02-07). Conditional grants stay deny until E05-01. ---
    rbac_conditions_enabled: bool = False

    # --- MFA / TOTP (E02-13). Fernet key (urlsafe-base64, 32 bytes) for the
    # secret at rest; empty in dev disables enrolment. Real secret store: ADR-0019.
    totp_encryption_key: str = ""

    # --- door control (E17-02). Fernet key for the door-open DTMF code at rest
    # (MASTER_PROMPT §30). Empty in dev/CI disables door-action profiles. Real
    # secret store: ADR-0019 / Epic 23.
    door_dtmf_encryption_key: str = ""
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

    # --- events: reactivation (E20-05) two-step confirm + accidental-series guard ---
    reactivation_token_ttl_seconds: int = 300
    reactivation_cooldown_seconds: int = 60

    # --- events: export (E20-06). JSON is always available; PDF is opt-in. ---
    export_pdf_enabled: bool = False

    # --- telephony (E11-06). Which telephony integration handles call control. ---
    telephony_integration_id: str = "telephony_mock"

    # --- video (E16-08). Which video integration serves camera trigger actions. ---
    video_integration_id: str = "coda_video"

    # --- weather (E18-06). Which weather integration the refresh singleton polls,
    # how often it ticks, and how long a data kind may go without a successful
    # refresh before its health is `stale`. ---
    weather_integration_id: str = "dwd"
    weather_refresh_seconds: int = 300
    weather_stale_after_seconds: int = 1800

    # --- retention (E20-07, docs/domain/retention-policy.md). Windows for
    # *derived / non-essential* data only. Events, domain events, audit and the
    # event history tables are NEVER pruned (0 would be meaningless there). ---
    retention_completed_command_days: int = 30  # idempotency replay window
    retention_completed_outbox_days: int = 90
    retention_processed_inbox_days: int = 90

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
