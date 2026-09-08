"""Encryption at rest for the SIP telephony secrets (roadmap E13-07, E13-09).

ADR-0033: the `telephony_sip` gateway config is DB-backed and UI-managed, and
the ARI password is a secret — it enters only in a ``PUT`` body over TLS, is
encrypted immediately, and is never returned by ``GET``, logged, or written to
an audit row. At connect time :func:`decrypt_ari_password` decrypts it in
process only, to build the ARI client.

ADR-0034 reuses the **same key** for the SIP trunk (ITSP) auth passwords —
:func:`encrypt_trunk_password` / :func:`decrypt_trunk_password`. They are
decrypted in-process only, at Asterisk-config render time, and the rendered
config is never written to BBZ's disk, logged, or audited.

ADR-0035 reuses it once more for the per-operator WebRTC SIP endpoint passwords
— :func:`encrypt_webrtc_password` / :func:`decrypt_webrtc_password`. Disclosed
once, over TLS, to the operator's own session by
``GET /api/v1/telephony/webrtc-credentials``; never logged or audited.

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


def encrypt_trunk_password(password: str) -> str:
    """A SIP trunk (ITSP) auth password, at rest (ADR-0034). Same key as the
    ARI password — one key for every SIP telephony secret."""
    return _fernet().encrypt(password.encode()).decode()


def decrypt_trunk_password(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise SipSecretsNotConfigured("cannot decrypt a SIP trunk password") from exc


def encrypt_webrtc_password(password: str) -> str:
    """A per-operator WebRTC SIP endpoint password, at rest (ADR-0035). Same key
    as the ARI / trunk passwords — one key for every SIP telephony secret."""
    return _fernet().encrypt(password.encode()).decode()


def decrypt_webrtc_password(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise SipSecretsNotConfigured("cannot decrypt a SIP WebRTC password") from exc
