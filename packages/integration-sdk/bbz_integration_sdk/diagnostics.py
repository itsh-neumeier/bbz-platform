"""Diagnostics / health interface every integration must expose.

Backs the admin "Integration Health" view (MASTER_PROMPT §8.14).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class DiagnosticsReport(BaseModel):
    integration_id: str
    state: HealthState = HealthState.UNKNOWN
    summary: str = ""
    checked_at: datetime | None = None
    last_success_at: datetime | None = None
    errors_since_healthy: int = 0
    # Free-form, integration-specific, but must not contain secrets (SECURITY.md).
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
