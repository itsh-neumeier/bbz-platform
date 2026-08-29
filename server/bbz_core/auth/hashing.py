"""Argon2id password hashing.

Parameters come from settings (``BBZ_ARGON2_*``), never hard-coded (ADR-0015).
``verify_password`` never raises and never leaks *why* a check failed.
"""

from __future__ import annotations

import contextlib
from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import Argon2Error, InvalidHashError

from bbz_core.settings import get_settings


@lru_cache
def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost_kib,
        parallelism=s.argon2_parallelism,
        type=Type.ID,
    )


@lru_cache
def _dummy_hash() -> str:
    """A real hash with the configured parameters, for the unknown-user path."""
    return _hasher().hash("bbz-nonexistent-account-placeholder")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """True iff ``password`` matches ``stored_hash``. Never raises."""
    try:
        return _hasher().verify(stored_hash, password)
    except (Argon2Error, InvalidHashError, TypeError, ValueError):
        return False


def verify_dummy(password: str) -> None:
    """Constant-work check for the unknown-user path. Result is ignored."""
    with contextlib.suppress(Argon2Error, InvalidHashError, TypeError, ValueError):
        _hasher().verify(_dummy_hash(), password)


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher().check_needs_rehash(stored_hash)
    except (Argon2Error, InvalidHashError):
        return True
