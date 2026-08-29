"""Local username/password authentication with failed-attempt lockout.

The service is storage-agnostic: it talks to a :class:`CredentialStore`
(implemented against the DB in E02-05's wiring). Lockout state lives in the
store so both application nodes see the same counter (E02-03 acceptance / HA).
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bbz_core.auth.hashing import hash_password, needs_rehash, verify_dummy, verify_password
from bbz_core.auth.policy import PasswordPolicy
from bbz_core.settings import get_settings


class LocalAuthResult(enum.StrEnum):
    SUCCESS = "success"
    BAD_CREDENTIALS = "bad_credentials"
    LOCKED = "locked"
    DISABLED = "disabled"


@dataclass(frozen=True)
class CredentialRecord:
    user_id: uuid.UUID
    auth_identity_id: uuid.UUID
    password_hash: str
    must_change: bool
    failed_attempts: int
    locked_until: _dt.datetime | None
    user_active: bool


@dataclass(frozen=True)
class AuthOutcome:
    result: LocalAuthResult
    user_id: uuid.UUID | None = None
    must_change_password: bool = False
    rehash: str | None = None  # new hash to persist if parameters changed


class CredentialStore(Protocol):
    async def get_by_username(self, username: str) -> CredentialRecord | None: ...
    async def record_failure(
        self, auth_identity_id: uuid.UUID, *, locked_until: _dt.datetime | None
    ) -> None: ...
    async def reset_failures(self, auth_identity_id: uuid.UUID) -> None: ...
    async def update_hash(self, auth_identity_id: uuid.UUID, new_hash: str) -> None: ...
    async def set_password(
        self, auth_identity_id: uuid.UUID, new_hash: str, *, must_change: bool
    ) -> None: ...


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class LocalAuthService:
    def __init__(
        self,
        store: CredentialStore,
        *,
        policy: PasswordPolicy | None = None,
        clock: Callable[[], _dt.datetime] = _utcnow,
    ) -> None:
        self._store = store
        self._policy = policy or PasswordPolicy.from_settings()
        self._now = clock

    async def authenticate(self, username: str, password: str) -> AuthOutcome:
        s = get_settings()
        record = await self._store.get_by_username(username)
        if record is None:
            verify_dummy(password)  # equalise timing for unknown accounts
            return AuthOutcome(LocalAuthResult.BAD_CREDENTIALS)

        now = self._now()
        if record.locked_until is not None and record.locked_until > now:
            return AuthOutcome(LocalAuthResult.LOCKED)
        if not record.user_active:
            return AuthOutcome(LocalAuthResult.DISABLED)

        if not verify_password(record.password_hash, password):
            attempts = record.failed_attempts + 1
            locked_until = (
                now + _dt.timedelta(seconds=s.login_lockout_seconds)
                if attempts >= s.login_max_failed_attempts
                else None
            )
            await self._store.record_failure(record.auth_identity_id, locked_until=locked_until)
            return AuthOutcome(
                LocalAuthResult.LOCKED if locked_until else LocalAuthResult.BAD_CREDENTIALS
            )

        await self._store.reset_failures(record.auth_identity_id)
        rehash: str | None = None
        if needs_rehash(record.password_hash):
            rehash = hash_password(password)
            await self._store.update_hash(record.auth_identity_id, rehash)
        return AuthOutcome(
            LocalAuthResult.SUCCESS,
            user_id=record.user_id,
            must_change_password=record.must_change,
            rehash=rehash,
        )

    async def set_password(
        self,
        auth_identity_id: uuid.UUID,
        new_password: str,
        *,
        username: str | None = None,
        must_change: bool = False,
    ) -> None:
        """Validate against policy and store a fresh hash. Raises PasswordPolicyError."""
        self._policy.validate(new_password, username=username)
        await self._store.set_password(
            auth_identity_id, hash_password(new_password), must_change=must_change
        )
