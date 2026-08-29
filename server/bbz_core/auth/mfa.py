"""TOTP second-factor flows: enrolment, activation, login challenge, disable."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass

from bbz_core.auth import totp as _totp
from bbz_core.infra.repositories.totp import TotpRepository


class ChallengeResult(enum.StrEnum):
    OK = "ok"
    BAD = "bad"
    RECOVERY_USED = "recovery_used"


@dataclass(frozen=True)
class EnrolmentStart:
    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class TotpService:
    def __init__(self, repo: TotpRepository) -> None:
        self._repo = repo

    async def is_active(self, auth_identity_id: uuid.UUID) -> bool:
        return await self._repo.is_active(auth_identity_id)

    async def begin_enrolment(self, auth_identity_id: uuid.UUID, *, account: str) -> EnrolmentStart:
        secret = _totp.new_secret()
        recovery = _totp.make_recovery_codes()
        await self._repo.start_enrolment(
            auth_identity_id, _totp.encrypt_secret(secret), recovery.hashes
        )
        return EnrolmentStart(
            secret=secret,
            otpauth_uri=_totp.otpauth_uri(secret, account=account),
            recovery_codes=recovery.plaintext,
        )

    async def activate(self, auth_identity_id: uuid.UUID, code: str) -> bool:
        row = await self._repo.get(auth_identity_id)
        if row is None or row.activated:
            return False
        step = _totp.verify_code(_totp.decrypt_secret(row.secret_ciphertext), code)
        if step is None:
            return False
        await self._repo.activate(auth_identity_id, step)
        return True

    async def challenge(self, auth_identity_id: uuid.UUID, code: str) -> ChallengeResult:
        row = await self._repo.get(auth_identity_id)
        if row is None or not row.activated:
            return ChallengeResult.BAD
        step = _totp.verify_code(
            _totp.decrypt_secret(row.secret_ciphertext), code, last_step=row.last_step
        )
        if step is not None:
            await self._repo.record_step(auth_identity_id, step)
            return ChallengeResult.OK
        if await self._repo.consume_recovery(auth_identity_id, _totp.hash_recovery_code(code)):
            return ChallengeResult.RECOVERY_USED
        return ChallengeResult.BAD

    async def disable(self, auth_identity_id: uuid.UUID) -> None:
        await self._repo.disable(auth_identity_id)
