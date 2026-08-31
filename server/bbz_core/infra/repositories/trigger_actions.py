"""Typed trigger actions (roadmap E15-06).

Runs the ordered, typed actions of one published trigger-rule version against a
normalized inbound signal. **Exactly-once**: each ``(provider_event_id,
rule_version_id, action_index)`` is claimed in ``trigger_executions`` (the
UNIQUE key from E15-02) — a replayed signal, or both HA nodes, run every action
at most once. A later action failing never un-does an earlier one (each is its
own transaction).

Core actions here (E15-06): ``create_event`` (transactional — one event with the
configured priority), ``attach_workflow`` (bind the template's published EPK
version to that event — idempotent), ``show_client_popup`` (one popup bound to a
workplace), ``notify`` (one ``external_action_outbox`` row). Camera / call
actions are E15-07/08; the engine that selects rules for a signal is E15-09.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.events import EventAggregate, EventPriority
from bbz_core.domain.triggers import TriggerActionType
from bbz_core.infra.event_stream import notify_event_appended
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.trigger_rules import (
    TriggerExecution,
    TriggerExecutionStatus,
    TriggerRuleVersion,
)
from bbz_core.infra.outbox import enqueue
from bbz_core.infra.repositories.events import EventRepository
from bbz_core.infra.repositories.workflow_engine import (
    NoPublishedVersionError,
    TemplateNotFoundError,
    WorkflowEngineService,
)

_DEFAULT_POPUP_TTL_SECONDS = 120
_KNOWN_FAILURES = (TemplateNotFoundError, NoPublishedVersionError)


class TriggerActionError(ValueError):
    """A rule action is malformed (missing required config, unknown type)."""


@dataclass
class _RunState:
    provider_event_id: uuid.UUID
    rule_version_id: uuid.UUID
    signal: dict[str, Any]
    actor_id: uuid.UUID | None
    #: results of earlier actions in this run — later actions (``attach_workflow``)
    #: may reference an event a ``create_event`` made
    results: dict[int, dict[str, Any]] = field(default_factory=dict)

    def last_event_id(self) -> uuid.UUID | None:
        for res in reversed(self.results.values()):
            if res.get("event_id"):
                return uuid.UUID(res["event_id"])
        return None


@dataclass(frozen=True)
class ActionOutcome:
    action_index: int
    action_type: str
    status: str
    result: dict[str, Any]


class TriggerActionService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def run_rule_version(
        self,
        *,
        provider_event_id: uuid.UUID,
        rule_version: TriggerRuleVersion,
        signal: dict[str, Any],
        actor_id: uuid.UUID | None = None,
    ) -> list[ActionOutcome]:
        state = _RunState(
            provider_event_id=provider_event_id,
            rule_version_id=rule_version.id,
            signal=signal,
            actor_id=actor_id,
        )
        outcomes: list[ActionOutcome] = []
        for index, raw_action in enumerate(rule_version.actions or []):
            outcome = await self._run_one(state, index, dict(raw_action))
            if outcome is not None:
                outcomes.append(outcome)
                state.results[index] = outcome.result
        return outcomes

    async def _run_one(
        self, state: _RunState, index: int, action: dict[str, Any]
    ) -> ActionOutcome | None:
        action_type = str(action.get("type", ""))
        await self._s.rollback()
        if action_type == TriggerActionType.ATTACH_WORKFLOW.value:
            return await self._run_attach_workflow(state, index, action)
        return await self._run_atomic(state, index, action_type, action)

    async def _run_atomic(
        self, state: _RunState, index: int, action_type: str, action: dict[str, Any]
    ) -> ActionOutcome | None:
        """claim + effect + finish + audit in one transaction — a failure rolls
        the whole thing back and is re-recorded as ``failed``."""
        succeeded = TriggerExecutionStatus.SUCCEEDED.value
        try:
            async with self._s.begin():
                if not await self._claim(state, index):
                    return None  # already executed for this signal (replay)
                result = await self._dispatch(state, index, action_type, action)
                await self._finish(state, index, succeeded, result)
                await self._audit(state, index, action_type, succeeded, result)
        except TriggerActionError as exc:
            return await self._record_failure(state, index, action_type, str(exc))
        if action_type == TriggerActionType.CREATE_EVENT.value:
            await notify_event_appended()
        return ActionOutcome(index, action_type, succeeded, result)

    async def _run_attach_workflow(
        self, state: _RunState, index: int, action: dict[str, Any]
    ) -> ActionOutcome | None:
        """``WorkflowEngineService.start_for_event`` self-commits and is
        idempotent, so the claim, the workflow start and the ledger update are
        three transactions rather than one."""
        succeeded = TriggerExecutionStatus.SUCCEEDED.value
        async with self._s.begin():
            if not await self._claim(state, index):
                return None
        try:
            result = await self._attach_workflow(state, action)
        except (*_KNOWN_FAILURES, TriggerActionError) as exc:
            return await self._record_failure(state, index, "attach_workflow", str(exc))
        await self._s.rollback()
        async with self._s.begin():
            await self._finish(state, index, succeeded, result)
            await self._audit(state, index, "attach_workflow", succeeded, result)
        return ActionOutcome(index, "attach_workflow", succeeded, result)

    # --- exactly-once ledger -----------------------------------------------

    async def _claim(self, state: _RunState, index: int) -> bool:
        stmt = (
            pg_insert(TriggerExecution)
            .values(
                provider_event_id=state.provider_event_id,
                rule_version_id=state.rule_version_id,
                action_index=index,
                status=TriggerExecutionStatus.PENDING.value,
            )
            .on_conflict_do_nothing(constraint="uq_trigger_executions_event_version_action")
            .returning(TriggerExecution.id)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def _row(self, state: _RunState, index: int) -> TriggerExecution:
        return (
            await self._s.execute(
                select(TriggerExecution).where(
                    TriggerExecution.provider_event_id == state.provider_event_id,
                    TriggerExecution.rule_version_id == state.rule_version_id,
                    TriggerExecution.action_index == index,
                )
            )
        ).scalar_one()

    async def _finish(
        self, state: _RunState, index: int, status: str, result: dict[str, Any]
    ) -> None:
        row = await self._row(state, index)
        row.status = status
        row.result = result
        row.completed_at = _dt.datetime.now(_dt.UTC)

    async def _audit(
        self, state: _RunState, index: int, action_type: str, status: str, result: dict[str, Any]
    ) -> None:
        await AuditService(self._s).write(
            AuditAction.TRIGGER_EXECUTED,
            actor_user_id=state.actor_id,
            target_type="trigger_rule_version",
            target_id=str(state.rule_version_id),
            after={
                "action_index": index,
                "action_type": action_type,
                "status": status,
                "provider_event_id": str(state.provider_event_id),
                "result": result,
            },
        )

    async def _record_failure(
        self, state: _RunState, index: int, action_type: str, error: str
    ) -> ActionOutcome:
        failed = TriggerExecutionStatus.FAILED.value
        result: dict[str, Any] = {"error": error}
        await self._s.rollback()
        async with self._s.begin():
            await self._claim(state, index)  # a no-op if the row already exists
            row = await self._row(state, index)
            if row.status == TriggerExecutionStatus.PENDING.value:
                row.status = failed
                row.result = result
                row.completed_at = _dt.datetime.now(_dt.UTC)
                await self._audit(state, index, action_type, failed, result)
        return ActionOutcome(index, action_type, failed, result)

    # --- action handlers -------------------------------------------------

    async def _dispatch(
        self, state: _RunState, index: int, action_type: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        if action_type == TriggerActionType.CREATE_EVENT.value:
            return await self._create_event(state, action)
        if action_type == TriggerActionType.SHOW_CLIENT_POPUP.value:
            return await self._show_client_popup(state, action)
        if action_type == TriggerActionType.NOTIFY.value:
            return await self._notify(state, index, action)
        raise TriggerActionError(f"action type not supported here: {action_type!r}")

    async def _create_event(self, state: _RunState, action: dict[str, Any]) -> dict[str, Any]:
        try:
            priority = EventPriority(action.get("priority", "high"))
        except ValueError as exc:
            raise TriggerActionError(f"invalid priority: {action.get('priority')!r}") from exc
        title = str(action.get("title") or f"Trigger: {state.signal.get('signal_type', 'signal')}")
        event_id = uuid.uuid4()
        agg = EventAggregate.create(
            event_id=event_id,
            title=title,
            priority=priority,
            actor_id=state.actor_id,
            description=action.get("description"),
            bbz_id=_as_uuid(action.get("bbz_id")),
            workplace_id=_as_uuid(action.get("workplace_id")),
            source="trigger",
        )
        await EventRepository(self._s).add(agg, actor_id=state.actor_id)
        return {"event_id": str(event_id), "priority": priority.value}

    async def _attach_workflow(self, state: _RunState, action: dict[str, Any]) -> dict[str, Any]:
        template_key = action.get("template_key")
        if not template_key:
            raise TriggerActionError("attach_workflow requires template_key")
        event_id = _as_uuid(action.get("event_id")) or state.last_event_id()
        if event_id is None:
            raise TriggerActionError("attach_workflow has no event to attach to")
        instance = await WorkflowEngineService(self._s).start_for_event(
            event_id, str(template_key), actor_id=state.actor_id
        )
        return {"event_id": str(event_id), "workflow_instance_id": str(instance.id)}

    async def _show_client_popup(self, state: _RunState, action: dict[str, Any]) -> dict[str, Any]:
        workplace_id = _as_uuid(action.get("workplace_id"))
        if workplace_id is None:
            raise TriggerActionError("show_client_popup requires workplace_id")
        ttl = int(action.get("ttl_seconds", _DEFAULT_POPUP_TTL_SECONDS))
        popup = ClientPopupEvent(
            workplace_id=workplace_id,
            kind=str(action.get("kind", "trigger")),
            payload=dict(action.get("payload") or {}),
            expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(seconds=ttl),
        )
        self._s.add(popup)
        await self._s.flush()
        return {"popup_id": str(popup.id), "workplace_id": str(workplace_id)}

    async def _notify(self, state: _RunState, index: int, action: dict[str, Any]) -> dict[str, Any]:
        dedupe = f"trigger:{state.provider_event_id}:{state.rule_version_id}:{index}"
        enqueued = await enqueue(
            self._s,
            dedupe_key=dedupe,
            action_type=TriggerActionType.NOTIFY.value,
            payload={
                "signal_type": state.signal.get("signal_type"),
                **(action.get("payload") or {}),
            },
        )
        return {"enqueued": enqueued}


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise TriggerActionError(f"not a uuid: {value!r}") from exc
