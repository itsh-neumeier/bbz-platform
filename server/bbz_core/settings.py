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
    #: git revision + build time, injected at container build (E22-04). Empty in
    #: a source checkout — /health/details then reports "unknown".
    build_revision: str = ""
    build_time: str = ""
    log_level: str = "INFO"
    log_json: bool = True
    # --- structured-log pipeline (E22-03) ---
    #: per-module overrides, "module=LEVEL,module=LEVEL" (a prefix match wins;
    #: e.g. "bbz_core.infra.leader=DEBUG,bbz_core.auth=WARNING")
    log_levels: str = ""
    #: drop a fraction of a noisy event, "event_name=keep_ratio,..."
    #: (e.g. "heartbeat=0.01,cluster_status_probe=0.1"); 0 drops it entirely
    log_sample: str = ""
    #: also write the JSON log lines to this file (a sidecar ships them —
    #: E22-03 does not run a log backend). Empty = stdout only.
    log_file: str = ""

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

    # --- auth: Entra ID / OIDC (E21-01). Empty issuer/client_id ⇒ the provider
    # stays a stub. `client_secret` blank ⇒ a public client (PKCE only). The real
    # values are an open external dependency; tests use a mock IdP.
    oidc_entra_issuer: str = ""
    oidc_entra_client_id: str = ""
    oidc_entra_client_secret: str = ""
    oidc_entra_redirect_uri: str = ""
    #: how long an unfinished OIDC login attempt (the `state` row) stays valid
    oidc_login_flow_ttl_seconds: int = 600
    #: allow just-in-time user creation on first external login (E21-02)
    oidc_jit_provisioning: bool = False
    #: role a JIT-created user gets before group mappings apply (empty ⇒ none)
    oidc_jit_default_role: str = ""

    # --- auth: LDAP / Active Directory (E21-03). Empty url ⇒ the provider stays a
    # stub. Only encrypted transport (ldaps:// or ldap:// + StartTLS). The bind
    # password is a secret (secrets_dir). Real values: open external dependency. ---
    ldap_url: str = ""  # comma-separated for a failover pool
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_user_filter: str = "(uid=%s)"
    ldap_group_search_base: str = ""
    ldap_group_filter: str = "(&(objectClass=groupOfNames)(member=%s))"
    #: attribute mapping — AD typically uid=sAMAccountName, name=displayName
    ldap_uid_attr: str = "uid"
    ldap_name_attr: str = "cn"
    ldap_mail_attr: str = "mail"
    ldap_start_tls: bool = True
    ldap_tls_verify: bool = True
    ldap_tls_ca_file: str = ""
    #: allow JIT user creation on first LDAP login (shares the OIDC group mappings)
    ldap_jit_provisioning: bool = False

    # --- auth: directory sync job (E21-04). A leader-elected singleton that
    # reconciles BBZ users/roles against the directory. Off unless enabled AND
    # ldap_url is set. Never hard-deletes; a run that would deactivate more than
    # ldap_sync_max_deactivations users aborts (a directory error must not mass
    # off-board). ---
    ldap_sync_enabled: bool = False
    ldap_sync_interval_seconds: int = 3600
    #: filter for enumerating every directory account (no ``%s``); AD uses
    #: ``(&(objectClass=user)(!(objectClass=computer)))``
    ldap_user_list_filter: str = "(objectClass=inetOrgPerson)"
    ldap_page_size: int = 500
    #: create a BBZ user for a directory account seen for the first time
    ldap_sync_provision: bool = True
    #: safety cap — abort the run (deactivate nobody) if more than this vanish at once
    ldap_sync_max_deactivations: int = 20

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

    # --- MFA policy engine + step-up (E21-05). Whether a login needs MFA is
    # role-based (`mfa_policies`); scope-based grants are a possible future
    # extension. Step-up re-checks freshness for a small, explicit set of
    # sensitive permissions. ---
    #: also enforce the policy on external (OIDC/LDAP) logins — they have no
    #: local TOTP today, so past the grace period they are blocked; off relaxes
    #: enforcement to local logins only
    mfa_policy_enforce_external: bool = True
    #: a step-up-verified session is fresh for this long before it must re-verify
    mfa_stepup_max_age_seconds: int = 300
    #: permissions that require a fresh step-up in addition to the permission
    #: itself (only routes guarded with ``require_stepup`` honour this)
    mfa_stepup_permissions: list[str] = Field(default_factory=lambda: ["permissions.manage"])

    # --- WebAuthn / FIDO2 (E21-06). The RP id is the registrable domain; the
    # origin(s) the browser sends must match. Empty rp_id ⇒ enrolment disabled. ---
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "BBZ / 3-S-Zentrale"
    #: allowed browser origin(s), comma-separated (e.g. https://bbz.example.org)
    webauthn_origins: str = ""
    #: require user verification (PIN/biometric) for a credential to count as MFA
    webauthn_require_user_verification: bool = True
    webauthn_challenge_ttl_seconds: int = 300

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

    # --- monitor routing (E19-04). Which monitor/KVM integration executes routes. ---
    monitor_integration_id: str = "monitor_mock"

    # --- weather (E18-06). Which weather integration the refresh singleton polls,
    # how often it ticks, and how long a data kind may go without a successful
    # refresh before its health is `stale`. ---
    weather_integration_id: str = "dwd"
    weather_refresh_seconds: int = 300
    weather_stale_after_seconds: int = 1800
    #: the label the radar frame series is cached + served under (E18-03/07)
    weather_radar_area: str = "mittelfranken"

    # --- retention (E20-07, docs/domain/retention-policy.md). Windows for
    # *derived / non-essential* data only. Events, domain events, audit and the
    # event history tables are NEVER pruned (0 would be meaningless there). ---
    retention_completed_command_days: int = 30  # idempotency replay window
    retention_completed_outbox_days: int = 90
    retention_processed_inbox_days: int = 90

    # --- observability: OpenTelemetry tracing (E22-01, ADR-0028). Tracing is on
    # by default (spans cost ~nothing without an exporter); the OTLP/HTTP
    # exporter is opt-in and toggled by config alone — never a code change. ---
    otel_enabled: bool = True
    #: "none" (default) keeps every span in-process; "otlp" ships over OTLP/HTTP
    otel_traces_exporter: Literal["none", "otlp"] = "none"
    #: collector base URL, e.g. http://otel-collector:4318 ("/v1/traces" is appended)
    otel_exporter_otlp_endpoint: str = ""
    #: extra OTLP headers as "key=value,key2=value2" (e.g. an auth token)
    otel_exporter_otlp_headers: str = ""
    #: head sampling ratio for traces without an inbound decision (0.0 to 1.0)
    otel_traces_sampler_ratio: float = 1.0

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
