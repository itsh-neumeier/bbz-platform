"""Audit action vocabulary. Extended by later epics (events, calls, RBAC, ...)."""

from __future__ import annotations

import enum


class AuditAction(enum.StrEnum):
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"
    MFA_ENROLLED = "MFA_ENROLLED"
    MFA_DISABLED = "MFA_DISABLED"
    MFA_CHALLENGE_FAILED = "MFA_CHALLENGE_FAILED"
    MFA_RECOVERY_USED = "MFA_RECOVERY_USED"
