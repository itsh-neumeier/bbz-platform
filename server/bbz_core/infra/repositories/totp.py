"""Storage for local TOTP secrets and recovery codes (E02-13)."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.identity import LocalTotp, LocalTotpRecoveryCode


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class TotpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, auth_identity_id: uuid.UUID) -> LocalTotp | None:
        return await self._s.get(LocalTotp, auth_identity_id)

    async def is_active(self, auth_identity_id: uuid.UUID) -> bool:
        row = await self._s.get(LocalTotp, auth_identity_id)
        return row is not None and row.activated

    async def start_enrolment(
        self, auth_identity_id: uuid.UUID, secret_ciphertext: str, recovery_hashes: list[str]
    ) -> None:
        stmt = insert(LocalTotp).values(
            auth_identity_id=auth_identity_id,
            secret_ciphertext=secret_ciphertext,
            activated=False,
            last_step=None,
            enrolled_at=_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[LocalTotp.auth_identity_id],
            set_={
                "secret_ciphertext": secret_ciphertext,
                "activated": False,
                "last_step": None,
                "enrolled_at": _now(),
            },
        )
        await self._s.execute(stmt)
        await self._s.execute(
            delete(LocalTotpRecoveryCode).where(
                LocalTotpRecoveryCode.auth_identity_id == auth_identity_id
            )
        )
        for h in recovery_hashes:
            self._s.add(LocalTotpRecoveryCode(auth_identity_id=auth_identity_id, code_hash=h))
        await self._s.commit()

    async def activate(self, auth_identity_id: uuid.UUID, step: int) -> None:
        await self._s.execute(
            update(LocalTotp)
            .where(LocalTotp.auth_identity_id == auth_identity_id)
            .values(activated=True, last_step=step)
        )
        await self._s.commit()

    async def record_step(self, auth_identity_id: uuid.UUID, step: int) -> None:
        await self._s.execute(
            update(LocalTotp)
            .where(LocalTotp.auth_identity_id == auth_identity_id)
            .values(last_step=step)
        )
        await self._s.commit()

    async def consume_recovery(self, auth_identity_id: uuid.UUID, code_hash: str) -> bool:
        row = (
            await self._s.execute(
                select(LocalTotpRecoveryCode).where(
                    LocalTotpRecoveryCode.auth_identity_id == auth_identity_id,
                    LocalTotpRecoveryCode.code_hash == code_hash,
                    LocalTotpRecoveryCode.used_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.used_at = _now()
        await self._s.commit()
        return True

    async def disable(self, auth_identity_id: uuid.UUID) -> None:
        await self._s.execute(
            delete(LocalTotp).where(LocalTotp.auth_identity_id == auth_identity_id)
        )
        await self._s.execute(
            delete(LocalTotpRecoveryCode).where(
                LocalTotpRecoveryCode.auth_identity_id == auth_identity_id
            )
        )
        await self._s.commit()
