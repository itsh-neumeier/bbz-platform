"""Local auth: hashing, password policy, lockout logic (no live database)."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import Iterator

import pytest

from bbz_core.auth import (
    LocalAuthResult,
    LocalAuthService,
    PasswordPolicy,
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    verify_password,
)
from bbz_core.auth.local import CredentialRecord


@pytest.fixture(autouse=True)
def _cheap_argon2() -> Iterator[None]:
    """Fast Argon2 parameters for the test run; reset the cached hasher."""
    from bbz_core.auth import hashing

    prev = {k: os.environ.get(k) for k in ("BBZ_ARGON2_MEMORY_COST_KIB", "BBZ_ARGON2_TIME_COST")}
    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# --- hashing ---------------------------------------------------------------


def test_hash_is_argon2id_and_verifies() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery staple") is True
    assert verify_password(h, "wrong") is False


def test_verify_never_raises_on_garbage() -> None:
    assert verify_password("not-a-hash", "x") is False
    assert verify_password("", "") is False
    assert needs_rehash("not-a-hash") is True


# --- policy ---------------------------------------------------------------


def test_policy_rejects_short_and_low_variety() -> None:
    p = PasswordPolicy(min_length=12, min_char_classes=3)
    with pytest.raises(PasswordPolicyError) as ei:
        p.validate("short1")
    assert any("12 characters" in r for r in ei.value.reasons)

    with pytest.raises(PasswordPolicyError):
        p.validate("alllowercaseletters")


def test_policy_rejects_common_and_username() -> None:
    p = PasswordPolicy(min_length=6, min_char_classes=1)
    with pytest.raises(PasswordPolicyError):
        p.validate("password")
    with pytest.raises(PasswordPolicyError):
        p.validate("Sichtleiter-2026!", username="sichtleiter")


def test_policy_accepts_strong_password() -> None:
    PasswordPolicy(min_length=12, min_char_classes=3).validate("Wolke7-Bahnhof!x")


# --- lockout / service --------------------------------------------------


class FakeStore:
    def __init__(self, rec: CredentialRecord | None) -> None:
        self.rec = rec
        self.calls: list[str] = []

    async def get_by_username(self, username: str) -> CredentialRecord | None:
        return self.rec

    async def record_failure(self, aid: uuid.UUID, *, locked_until: _dt.datetime | None) -> None:
        assert self.rec is not None
        self.rec = CredentialRecord(
            **{
                **self.rec.__dict__,
                "failed_attempts": self.rec.failed_attempts + 1,
                "locked_until": locked_until,
            }
        )
        self.calls.append("record_failure")

    async def reset_failures(self, aid: uuid.UUID) -> None:
        self.calls.append("reset_failures")

    async def update_hash(self, aid: uuid.UUID, new_hash: str) -> None:
        self.calls.append("update_hash")

    async def set_password(self, aid: uuid.UUID, new_hash: str, *, must_change: bool) -> None:
        self.calls.append("set_password")


def _record(**over: object) -> CredentialRecord:
    base: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "auth_identity_id": uuid.uuid4(),
        "password_hash": hash_password("S3cret-passphrase!"),
        "must_change": False,
        "failed_attempts": 0,
        "locked_until": None,
        "user_active": True,
    }
    base.update(over)
    return CredentialRecord(**base)  # type: ignore[arg-type]


async def test_authenticate_success() -> None:
    rec = _record()
    svc = LocalAuthService(FakeStore(rec))
    out = await svc.authenticate("alice", "S3cret-passphrase!")
    assert out.result is LocalAuthResult.SUCCESS
    assert out.user_id == rec.user_id


async def test_unknown_user_is_bad_credentials() -> None:
    svc = LocalAuthService(FakeStore(None))
    out = await svc.authenticate("nobody", "whatever")
    assert out.result is LocalAuthResult.BAD_CREDENTIALS


async def test_wrong_password_increments_then_locks() -> None:
    store = FakeStore(_record())
    svc = LocalAuthService(store)
    for _ in range(4):
        assert (await svc.authenticate("a", "nope")).result is LocalAuthResult.BAD_CREDENTIALS
    # 5th failure trips the lockout
    assert (await svc.authenticate("a", "nope")).result is LocalAuthResult.LOCKED
    assert store.rec is not None and store.rec.locked_until is not None


async def test_locked_account_rejects_even_correct_password() -> None:
    future = _dt.datetime.now(_dt.UTC) + _dt.timedelta(minutes=10)
    svc = LocalAuthService(FakeStore(_record(locked_until=future)))
    out = await svc.authenticate("a", "S3cret-passphrase!")
    assert out.result is LocalAuthResult.LOCKED


async def test_disabled_user_rejected() -> None:
    svc = LocalAuthService(FakeStore(_record(user_active=False)))
    assert (await svc.authenticate("a", "S3cret-passphrase!")).result is LocalAuthResult.DISABLED


async def test_success_resets_failures_and_flags_must_change() -> None:
    store = FakeStore(_record(failed_attempts=2, must_change=True))
    out = await LocalAuthService(store).authenticate("a", "S3cret-passphrase!")
    assert out.result is LocalAuthResult.SUCCESS
    assert out.must_change_password is True
    assert "reset_failures" in store.calls


async def test_set_password_enforces_policy() -> None:
    store = FakeStore(_record())
    svc = LocalAuthService(store, policy=PasswordPolicy(min_length=12, min_char_classes=3))
    with pytest.raises(PasswordPolicyError):
        await svc.set_password(uuid.uuid4(), "weak")
    await svc.set_password(uuid.uuid4(), "Wolke7-Bahnhof!x")
    assert "set_password" in store.calls
