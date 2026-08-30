"""Provider-event inbox: persist + deduplicate inbound external events (ADR-0011).

``ingest`` is the single entry point every provider edge calls before handing
anything to the trigger engine. It returns whether the event is ``new`` or a
``duplicate``; a duplicate is never processed again (provider reconnect replay,
or the other HA node already ingested it).

When the provider has no stable event id, the dedupe key is derived
deterministically from documented fields: ``provider`` + a SHA-256 of the
normalized payload (key-order-insensitive).
"""

from __future__ import annotations

import datetime as _dt
import enum
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.logging import correlation_id


class IngestOutcome(enum.StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class IngestResult:
    outcome: IngestOutcome
    inbox_id: uuid.UUID
    dedupe_key: str


def _payload_hash(normalized: dict[str, Any]) -> str:
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def derive_dedupe_key(
    provider: str, provider_event_id: str | None, normalized: dict[str, Any]
) -> str:
    if provider_event_id:
        return f"{provider}:{provider_event_id}"
    return f"{provider}:sha256:{_payload_hash(normalized)}"


async def ingest(
    session: AsyncSession,
    *,
    provider: str,
    normalized: dict[str, Any],
    provider_event_id: str | None = None,
    raw_ref: str | None = None,
    raw_hash: str | None = None,
    dedupe_key: str | None = None,
) -> IngestResult:
    key = dedupe_key or derive_dedupe_key(provider, provider_event_id, normalized)
    stmt = (
        pg_insert(ProviderEventInbox)
        .values(
            provider=provider,
            provider_event_id=provider_event_id,
            dedupe_key=key,
            raw_ref=raw_ref,
            raw_hash=raw_hash,
            normalized=normalized,
            correlation_id=correlation_id.get(),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(ProviderEventInbox.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        return IngestResult(IngestOutcome.NEW, inserted, key)
    existing = (
        await session.execute(
            select(ProviderEventInbox.id).where(ProviderEventInbox.dedupe_key == key)
        )
    ).scalar_one()
    return IngestResult(IngestOutcome.DUPLICATE, existing, key)


async def mark_processed(session: AsyncSession, inbox_id: uuid.UUID) -> None:
    row = await session.get(ProviderEventInbox, inbox_id)
    if row is not None and row.processed_at is None:
        row.processed_at = _dt.datetime.now(_dt.UTC)
