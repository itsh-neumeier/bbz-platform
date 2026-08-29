"""Audit log (MASTER_PROMPT §17).

``AuditService.write`` (E04-02) is the primary path: it appends an immutable row
**in the caller's transaction**, enforces a mandatory ``reason`` for flagged
actions, and offers :func:`changed_fields` for before/after diffs. ``AuditWriter``
is the older read + fire-and-forget writer kept for the auth events and the
basic filtered read (E02-12); the generic query API is E04-04.
"""

from __future__ import annotations

from bbz_core.audit.actions import CRITICAL_ACTIONS, AuditAction
from bbz_core.audit.service import (
    AuditNotInTransactionError,
    AuditReasonRequiredError,
    AuditService,
    changed_fields,
)
from bbz_core.audit.writer import AuditRecord, AuditWriter

__all__ = [
    "CRITICAL_ACTIONS",
    "AuditAction",
    "AuditNotInTransactionError",
    "AuditReasonRequiredError",
    "AuditRecord",
    "AuditService",
    "AuditWriter",
    "changed_fields",
]
