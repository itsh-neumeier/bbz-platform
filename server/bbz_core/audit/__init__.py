"""Audit log — seeded with authentication events (E02-12).

``AuditWriter`` appends immutable rows. The full audit-write service (in-tx with
the state change, before/after diffing, mandatory-reason enforcement) is E04-02;
the generic query API is E04-04. What exists here is enough for auth events and
a basic filtered read.
"""

from __future__ import annotations

from bbz_core.audit.actions import AuditAction
from bbz_core.audit.writer import AuditRecord, AuditWriter

__all__ = ["AuditAction", "AuditRecord", "AuditWriter"]
