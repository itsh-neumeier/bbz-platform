"""TOTP (RFC 6238) enrolment, verification, recovery codes.

The shared secret is stored encrypted (Fernet, key from
``BBZ_TOTP_ENCRYPTION_KEY``). Recovery codes are stored only as SHA-256 hashes
and are single-use. Nothing here ever returns or logs the raw secret except the
one-time enrolment response.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from bbz_core.settings import get_settings

_RECOVERY_COUNT = 10


class TotpNotConfiguredError(RuntimeError):
    """No encryption key configured — enrolment is unavailable in this env."""


def _fernet() -> Fernet:
    key = get_settings().totp_encryption_key
    if not key:
        raise TotpNotConfiguredError("BBZ_TOTP_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def generate_key() -> str:
    """A fresh Fernet key — for operators setting BBZ_TOTP_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise TotpNotConfiguredError("cannot decrypt TOTP secret") from exc


def otpauth_uri(secret: str, *, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=get_settings().totp_issuer)


def verify_code(
    secret: str, code: str, *, last_step: int | None = None, now: float | None = None
) -> int | None:
    """Return the matched time-step (persist it as ``last_step`` to block reuse),
    or ``None`` if the code is invalid or already used."""
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    step = int((now if now is not None else time.time()) // totp.interval)
    for candidate in (step - 1, step, step + 1):  # +-1 window for clock skew
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(totp.at(candidate * totp.interval), code):
            return candidate
    return None


@dataclass(frozen=True)
class RecoveryCodes:
    plaintext: list[str]
    hashes: list[str]


def make_recovery_codes() -> RecoveryCodes:
    plain = [
        f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}"
        for _ in range(_RECOVERY_COUNT)
    ]
    return RecoveryCodes(plain, [hash_recovery_code(c) for c in plain])


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
