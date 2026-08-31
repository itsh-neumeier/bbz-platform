"""Encryption at rest for door-open DTMF codes (E17-02).

MASTER_PROMPT §30, .ai/SECURITY.md "Door control security", ADR-0004. The
plaintext code lives only transiently: in a request body over TLS, and at
door-open time (E17-05) in memory just long enough to hand to the telephony
provider. It is never logged, echoed, put in an event / audit payload, or
written to disk except as this ciphertext.

Mirrors :mod:`bbz_core.auth.totp` — the concrete runtime secret store is ADR-0019
/ Epic 23; until then the key comes from ``BBZ_DOOR_DTMF_ENCRYPTION_KEY``.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from bbz_core.settings import get_settings


class DoorSecretsNotConfigured(RuntimeError):
    """No door-DTMF encryption key configured — door profiles are unavailable."""


def _fernet() -> Fernet:
    key = get_settings().door_dtmf_encryption_key
    if not key:
        raise DoorSecretsNotConfigured("BBZ_DOOR_DTMF_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def generate_key() -> str:
    """A fresh Fernet key — for operators setting BBZ_DOOR_DTMF_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def encrypt_dtmf(code: str) -> str:
    return _fernet().encrypt(code.encode()).decode()


def decrypt_dtmf(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise DoorSecretsNotConfigured("cannot decrypt a door DTMF profile") from exc
