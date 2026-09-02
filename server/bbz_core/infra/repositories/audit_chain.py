"""Audit-log hash chain — sealing and verification (E23-09, MASTER_PROMPT §17).

``audit_events`` is already append-only (0016). This adds tamper *detection*: a
worker seals each new audit row into ``audit_chain_links`` with
``row_hash = sha256(prev_hash + sha256(canonical(row)))``, and periodically
re-walks the chain. A recomputed hash that no longer matches, a gap in ``seq``,
or a linked audit row that has vanished all fail :meth:`AuditChainService.verify`
— the worker then writes ``AUDIT_INTEGRITY_ALERT``.

Sealing is deferred (not in the audit-write path) so it adds **zero** overhead
to the triggering transaction. New rows are unsealed for at most one worker
interval; the ``seq`` identity column still makes a deleted-in-that-window row
detectable as a gap once the chain catches up.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditChainLink, AuditEvent

GENESIS = "0" * 64
_LOCK_KEY = 82_309  # pg_advisory_xact_lock namespace for the sealer (E23-09)

_ROW_FIELDS = (
    "seq",
    "occurred_at_utc",
    "node_id",
    "action",
    "actor_user_id",
    "actor_client_id",
    "workplace_id",
    "target_type",
    "target_id",
    "before",
    "after",
    "reason",
    "correlation_id",
    "event_seq_ref",
)


@dataclass(frozen=True)
class SealResult:
    sealed: int
    head_seq: int
    head_hash: str


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    head_seq: int
    head_hash: str
    first_bad_seq: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ChainLinkView:
    seq: int
    audit_event_id: uuid.UUID
    prev_hash: str
    row_hash: str
    action: str
    occurred_at_utc: str


def _row_digest(row: dict[str, object]) -> str:
    payload = json.dumps(
        {k: row.get(k) for k in _ROW_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _link_hash(prev_hash: str, row_digest: str) -> str:
    return hashlib.sha256(f"{prev_hash}{row_digest}".encode()).hexdigest()


class AuditChainService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _head(self) -> tuple[int, str]:
        row = (
            await self._s.execute(
                select(AuditChainLink.seq, AuditChainLink.row_hash)
                .order_by(AuditChainLink.seq.desc())
                .limit(1)
            )
        ).first()
        return (row[0], row[1]) if row else (0, GENESIS)

    async def seal(self) -> SealResult:
        """Append a link for every audit row past the current chain head."""
        await self._s.rollback()
        async with self._s.begin():
            await self._s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
            head_seq, prev = await self._head()
            rows = (
                await self._s.execute(
                    select(*[getattr(AuditEvent, f) for f in _ROW_FIELDS], AuditEvent.id)
                    .where(AuditEvent.seq > head_seq)
                    .order_by(AuditEvent.seq)
                )
            ).all()
            sealed = 0
            for row in rows:
                data = dict(zip(_ROW_FIELDS, row, strict=False))
                seq = int(row[0])
                row_hash = _link_hash(prev, _row_digest(data))
                self._s.add(
                    AuditChainLink(
                        seq=seq,
                        audit_event_id=row[-1],
                        prev_hash=prev,
                        row_hash=row_hash,
                    )
                )
                prev = row_hash
                head_seq = seq
                sealed += 1
        return SealResult(sealed=sealed, head_seq=head_seq, head_hash=prev)

    async def verify(self, *, limit: int | None = None) -> VerifyResult:
        """Re-walk the sealed chain and recompute every hash."""
        await self._s.rollback()
        links = (
            (
                await self._s.execute(
                    select(AuditChainLink).order_by(AuditChainLink.seq).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not links:
            return VerifyResult(ok=True, checked=0, head_seq=0, head_hash=GENESIS)

        by_seq = {
            r[0]: dict(zip(_ROW_FIELDS, r[1:], strict=False))
            for r in (
                await self._s.execute(
                    select(AuditEvent.seq, *[getattr(AuditEvent, f) for f in _ROW_FIELDS]).where(
                        AuditEvent.seq.in_([link.seq for link in links])
                    )
                )
            ).all()
        }

        prev = GENESIS
        expected_seq: int | None = None
        for link in links:
            if expected_seq is not None and link.seq != expected_seq:
                return self._bad(
                    link.seq, f"seq gap: expected {expected_seq}, got {link.seq}", prev
                )
            expected_seq = link.seq + 1
            if link.prev_hash != prev:
                return self._bad(link.seq, "prev_hash does not match the previous link", prev)
            row = by_seq.get(link.seq)
            if row is None:
                return self._bad(link.seq, "the audit row for this link has vanished", prev)
            if _link_hash(prev, _row_digest(row)) != link.row_hash:
                return self._bad(link.seq, "row content no longer hashes to row_hash", prev)
            prev = link.row_hash

        return VerifyResult(
            ok=True, checked=len(links), head_seq=links[-1].seq, head_hash=links[-1].row_hash
        )

    @staticmethod
    def _bad(seq: int, detail: str, head_hash: str) -> VerifyResult:
        return VerifyResult(
            ok=False,
            checked=seq,
            head_seq=seq,
            head_hash=head_hash,
            first_bad_seq=seq,
            detail=detail,
        )

    async def export(self, *, after_seq: int = 0, limit: int = 1000) -> list[ChainLinkView]:
        rows = (
            await self._s.execute(
                select(
                    AuditChainLink.seq,
                    AuditChainLink.audit_event_id,
                    AuditChainLink.prev_hash,
                    AuditChainLink.row_hash,
                    AuditEvent.action,
                    AuditEvent.occurred_at_utc,
                )
                .join(AuditEvent, AuditEvent.seq == AuditChainLink.seq)
                .where(AuditChainLink.seq > after_seq)
                .order_by(AuditChainLink.seq)
                .limit(limit)
            )
        ).all()
        return [
            ChainLinkView(
                seq=r[0],
                audit_event_id=r[1],
                prev_hash=r[2],
                row_hash=r[3],
                action=r[4],
                occurred_at_utc=r[5].isoformat(),
            )
            for r in rows
        ]
