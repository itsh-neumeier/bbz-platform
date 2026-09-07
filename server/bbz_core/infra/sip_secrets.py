"""Encryption at rest for the SIP gateway's ARI password (roadmap E13-07).

ADR-0033: the `telephony_sip` gateway config is DB-backed and UI-managed, and
the ARI password is a secret — it enters only in a ``PUT`` body over TLS, is
encrypted immediately, and is never returned by ``GET``, logged, or written to
an audit row. At connect time :func:`decrypt_ari_password` decrypts it in
process only, to build the ARI client.

Mirrors :mod:`bbz_core.infra.door_secrets` exactly — the concrete runtime
secret store is ADR-0019 / Epic 23; until then the key comes from
``BBZ_SIP_ENCRYPTION_KEY``.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from bbz_core.settings import get_settings


class SipSecretsNotConfigured(RuntimeError):
    """No SIP encryption key configured — the SIP gateway config is unavailable."""


def _fernet() -> Fernet:
    key = get_settings().sip_encryption_key
    if not key:
        raise SipSecretsNotConfigured("BBZ_SIP_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def generate_key() -> str:
    """A fresh Fernet key — for operators setting BBZ_SIP_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def encrypt_ari_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_ari_password(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise SipSecretsNotConfigured("cannot decrypt the SIP ARI password") from exc
