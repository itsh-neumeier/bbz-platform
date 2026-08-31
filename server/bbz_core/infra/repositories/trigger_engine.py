"""Trigger-execution engine (roadmap E15-09).

After the E04-07 provider inbox has deduplicated a normalized inbound signal
(E15-04), the engine:

1. loads every **published** trigger rule and its published version;
2. selects the matching rules, deterministically ordered by ``(priority,
   rule_id)`` (E15-05);
3. runs each rule version's actions through :class:`TriggerActionService`, where
   every ``(provider_event_id, rule_version_id, action_index)`` is claimed once
   (E15-06);
4. marks the inbox row processed.

**Exactly-once, active/active** (``.ai/TECHNICAL_TRIGGERS.md``): a
double-delivered provider event is a duplicate at the inbox, and every action is
guarded by the ``trigger_executions`` UNIQUE key — so re-processing an
unprocessed inbox row after a crash resumes without duplicating anything.
``resume_unprocessed`` is the recovery entry point.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import CandidateRule, select_matching_rules
from bbz_core.infra.inbox import mark_processed
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.trigger_rules import TriggerLifecycle, TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_actions import ActionOutcome, TriggerActionService

_PUBLISHED = TriggerLifecycle.PUBLISHED.value


@dataclass(frozen=True)
class EngineResult:
    inbox_id: uuid.UUID
    signal_type: str | None
    matched_rules: int
    processed: bool
    actions: list[ActionOutcome] = field(default_factory=list)


class TriggerEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def process_inbox_event(
        self, inbox_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> EngineResult:
        await self._s.rollback()
        row = await self._s.get(ProviderEventInbox, inbox_id)
        if row is None or row.processed_at is not None:
            return EngineResult(inbox_id, None, 0, processed=row is not None, actions=[])

        signal = dict(row.normalized)
        signal_type = signal.get("signal_type")
        if not signal_type:
            # not a normalized inbound signal (e.g. a raw telephony event that
            # only feeds the call lifecycle) — nothing to trigger on
            await self._mark(inbox_id)
            return EngineResult(inbox_id, None, 0, processed=True, actions=[])

        matched = select_matching_rules(await self._candidates(), signal)
        outcomes: list[ActionOutcome] = []
        for cand in matched:
            version = await self._published_version(cand.rule_id)
            if version is None:
                continue
            outcomes.extend(
                await TriggerActionService(self._s).run_rule_version(
                    provider_event_id=inbox_id,
                    rule_version=version,
                    signal=signal,
                    actor_id=actor_id,
                )
            )

        await self._mark(inbox_id)
        return EngineResult(
            inbox_id, str(signal_type), len(matched), processed=True, actions=outcomes
        )

    async def resume_unprocessed(
        self, *, limit: int = 50, actor_id: uuid.UUID | None = None
    ) -> list[EngineResult]:
        """Re-process inbox rows left unprocessed by a crash — safe, exactly-once."""
        await self._s.rollback()
        ids = list(
            (
                await self._s.execute(
                    select(ProviderEventInbox.id)
                    .where(ProviderEventInbox.processed_at.is_(None))
                    .order_by(ProviderEventInbox.received_at.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [await self.process_inbox_event(i, actor_id=actor_id) for i in ids]

    # --- internals -----------------------------------------------------

    async def _candidates(self) -> list[CandidateRule]:
        rows = (
            await self._s.execute(
                select(TriggerRule.id, TriggerRule.priority, TriggerRuleVersion.conditions)
                .join(TriggerRuleVersion, TriggerRuleVersion.rule_id == TriggerRule.id)
                .where(
                    TriggerRule.lifecycle == _PUBLISHED,
                    TriggerRuleVersion.lifecycle == _PUBLISHED,
                )
                .order_by(TriggerRuleVersion.version_no.desc())
            )
        ).all()
        seen: set[uuid.UUID] = set()
        candidates: list[CandidateRule] = []
        for rule_id, priority, conditions in rows:
            if rule_id in seen:  # keep only the highest published version per rule
                continue
            seen.add(rule_id)
            candidates.append(CandidateRule(rule_id, priority, conditions))
        return candidates

    async def _published_version(self, rule_id: uuid.UUID) -> TriggerRuleVersion | None:
        return (
            await self._s.execute(
                select(TriggerRuleVersion)
                .where(
                    TriggerRuleVersion.rule_id == rule_id,
                    TriggerRuleVersion.lifecycle == _PUBLISHED,
                )
                .order_by(TriggerRuleVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _mark(self, inbox_id: uuid.UUID) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await mark_processed(self._s, inbox_id)


async def process_signal(
    session: AsyncSession,
    *,
    signal: dict[str, Any],
    provider_event_id: str | None = None,
    dedupe_key: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> EngineResult:
    """Record a normalized inbound signal (dedupe) then run the engine on it.

    The convenience an integration edge calls after normalizing a provider
    event. A duplicate signal is a no-op (the inbox rejects it and the row is
    already processed).
    """
    from bbz_core.infra.inbound_signals import record_inbound_signal

    await session.rollback()
    async with session.begin():
        result = await record_inbound_signal(
            session,
            signal=signal,
            provider_event_id=provider_event_id,
            dedupe_key=dedupe_key,
        )
    return await TriggerEngine(session).process_inbox_event(result.inbox_id, actor_id=actor_id)
