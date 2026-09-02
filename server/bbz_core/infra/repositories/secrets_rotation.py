"""Runtime secret rotation (roadmap E23-01, ADR-0019).

A secret is rotated *out of band* — the orchestrator (or, later, Vault) updates
the mounted file / KV entry. :meth:`SecretsRotationService.reload` then re-reads
the tracked secrets, and for each whose value now differs from what this process
has loaded it clears the settings cache and audits ``SECRET_ROTATED`` (the field
name only, never a value).

The running ``Settings`` *is* the baseline — no extra state to persist, and a
fresh process (which loads secrets from the file) sees nothing to reload.
Env-sourced secrets cannot change in a running process, so only file / store
secrets rotate live; that is by design.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.secrets import SECRET_FIELDS, get_secret_provider
from bbz_core.settings import get_settings

#: settings field -> the provider key (``BBZ_`` prefix, lower-case)
_FIELD_TO_KEY = {field: f"bbz_{field}" for field in SECRET_FIELDS}


class SecretsRotationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def reload(self, *, actor_id: uuid.UUID | None = None) -> list[str]:
        """Re-read the tracked secrets; audit + cache-bust the ones that changed.
        Returns the changed field names."""
        provider = get_secret_provider()
        provider.invalidate()  # bypass the TTL cache — read fresh from the store
        current = get_settings()

        changed = [
            field
            for field, key in _FIELD_TO_KEY.items()
            if (fresh := provider.get(key)) is not None and fresh != getattr(current, field)
        ]
        if not changed:
            return []

        get_settings.cache_clear()  # next get_settings() re-reads the new values
        await self._s.rollback()
        async with self._s.begin():
            for field in changed:
                await AuditService(self._s).write(
                    AuditAction.SECRET_ROTATED,
                    actor_user_id=actor_id,
                    target_type="secret",
                    target_id=field,
                    after={"secret": field, "rotated": True},
                )
        return changed
