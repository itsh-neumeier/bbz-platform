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

    @property
    def database_url_sync(self) -> str:
        """Sync DSN for Alembic (psycopg-style driver stripped to plain)."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
