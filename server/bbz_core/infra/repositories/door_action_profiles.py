"""Door-open action profiles: create / read / update the encrypted DTMF (E17-02).

The plaintext code enters once (a POST / PATCH body over TLS), is encrypted
immediately, and is never returned, logged or audited (MASTER_PROMPT §30,
.ai/SECURITY.md). :meth:`resolve_dtmf` decrypts it — only the door-open flow
(E17-05) calls that, and it must not log the result.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.door_secrets import decrypt_dtmf, encrypt_dtmf
from bbz_core.infra.models.door_action_profiles import DoorActionProfile

_DTMF_ALPHABET = set("0123456789ABCD*#")
_MUTABLE = frozenset({"name", "dtmf_code", "post_dtmf_delay_ms", "auto_hangup"})


class DoorProfileError(ValueError):
    pass


class DoorProfileNotFoundError(DoorProfileError):
    pass


class InvalidDoorProfileError(DoorProfileError):
    """A field value is not acceptable. The message never echoes the DTMF code."""


def _check_code(code: str) -> None:
    if not code or len(code) > 32 or any(c not in _DTMF_ALPHABET for c in code.upper()):
        raise InvalidDoorProfileError("dtmf code must be 1-32 characters of 0-9 A-D * #")


@dataclass(frozen=True)
class ProfileView:
    id: uuid.UUID
    name: str
    post_dtmf_delay_ms: int
    auto_hangup: bool
    configured: bool
    created_by: uuid.UUID | None
    created_at: Any
    updated_at: Any


def _view(p: DoorActionProfile) -> ProfileView:
    return ProfileView(
        id=p.id,
        name=p.name,
        post_dtmf_delay_ms=p.post_dtmf_delay_ms,
        auto_hangup=p.auto_hangup,
        configured=bool(p.dtmf_ciphertext),
        created_by=p.created_by,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class DoorActionProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_views(self) -> list[ProfileView]:
        rows = (
            (
                await self._s.execute(
                    select(DoorActionProfile)
                    .order_by(DoorActionProfile.name)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return [_view(p) for p in rows]

    async def get(self, profile_id: uuid.UUID) -> ProfileView:
        return _view(await self._load(profile_id))

    async def create(
        self,
        *,
        name: str,
        dtmf_code: str,
        post_dtmf_delay_ms: int = 500,
        auto_hangup: bool = True,
        actor_id: uuid.UUID | None,
    ) -> ProfileView:
        _check_code(dtmf_code)
        await self._s.rollback()
        profile = DoorActionProfile(
            name=name,
            dtmf_ciphertext=encrypt_dtmf(dtmf_code),
            post_dtmf_delay_ms=post_dtmf_delay_ms,
            auto_hangup=auto_hangup,
            created_by=actor_id,
        )
        self._s.add(profile)
        await self._s.flush()
        await self._audit(
            AuditAction.DOOR_PROFILE_CREATED,
            profile.id,
            actor_id,
            after={
                "name": name,
                "post_dtmf_delay_ms": post_dtmf_delay_ms,
                "auto_hangup": auto_hangup,
            },
        )
        await self._s.commit()
        return await self.get(profile.id)

    async def update(
        self, profile_id: uuid.UUID, changes: dict[str, Any], *, actor_id: uuid.UUID | None
    ) -> ProfileView:
        unknown = set(changes) - _MUTABLE
        if unknown:
            raise InvalidDoorProfileError(f"cannot change: {', '.join(sorted(unknown))}")
        await self._s.rollback()
        profile = await self._load(profile_id)

        changed: list[str] = []
        if "name" in changes and changes["name"] != profile.name:
            profile.name = str(changes["name"])
            changed.append("name")
        if (
            "post_dtmf_delay_ms" in changes
            and int(changes["post_dtmf_delay_ms"]) != profile.post_dtmf_delay_ms
        ):
            profile.post_dtmf_delay_ms = int(changes["post_dtmf_delay_ms"])
            changed.append("post_dtmf_delay_ms")
        if "auto_hangup" in changes and bool(changes["auto_hangup"]) != profile.auto_hangup:
            profile.auto_hangup = bool(changes["auto_hangup"])
            changed.append("auto_hangup")
        if changes.get("dtmf_code") is not None:
            _check_code(changes["dtmf_code"])
            profile.dtmf_ciphertext = encrypt_dtmf(changes["dtmf_code"])
            changed.append("dtmf_code")  # the field NAME only — never the value

        if not changed:
            await self._s.rollback()
            return await self.get(profile_id)
        await self._audit(
            AuditAction.DOOR_PROFILE_UPDATED,
            profile_id,
            actor_id,
            after={"changed": sorted(changed)},
        )
        await self._s.commit()
        return await self.get(profile_id)

    async def delete(self, profile_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        profile = await self._load(profile_id)
        await self._audit(
            AuditAction.DOOR_PROFILE_DELETED, profile_id, actor_id, after={"name": profile.name}
        )
        await self._s.execute(delete(DoorActionProfile).where(DoorActionProfile.id == profile_id))
        await self._s.commit()

    async def resolve_dtmf(self, profile_id: uuid.UUID) -> tuple[str, int, bool]:
        """Decrypt for the door-open flow (E17-05). The caller must not log this."""
        p = await self._load(profile_id)
        return decrypt_dtmf(p.dtmf_ciphertext), p.post_dtmf_delay_ms, p.auto_hangup

    # --- internals ---

    async def _load(self, profile_id: uuid.UUID) -> DoorActionProfile:
        p = (
            await self._s.execute(
                select(DoorActionProfile)
                .where(DoorActionProfile.id == profile_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if p is None:
            raise DoorProfileNotFoundError(str(profile_id))
        return p

    async def _audit(
        self,
        action: AuditAction,
        profile_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        *,
        after: dict[str, Any],
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="door_action_profile",
            target_id=str(profile_id),
            after=after,
        )
