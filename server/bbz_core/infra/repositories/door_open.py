"""Transactional, idempotent door-open flow (roadmap E17-05, ADR-0025).

An operator presses "Öffnen" on the doorbell popup → this runs the Siedle
door-open sequence over the **active telephony provider**:

1. authorize ``door.open`` (the API route)
2. one idempotent command per ``X-Command-Id`` (a repeat → replay, no 2nd open)
3. answer the doorbell call if it is still ringing
4. wait for CONNECTED / media, bounded by ``door_open_timeout_seconds``
5. send the configured DTMF sequence **exactly once**
6. wait ``post_dtmf_delay_ms``
7. auto-hang up (if the profile says so)
8. audited outcome — ``DOOR_OPEN_REQUESTED`` / ``DOOR_OPEN_RESULT``

The DTMF sequence is resolved from ``door_action_profiles`` (Fernet, E17-02)
**transiently** — held only in a local, passed to ``send_dtmf``, never persisted,
logged, or put in an audit / event payload (ADR-0025 / §30). Each provider step
uses a deterministic derived ``command_id`` (``door:<cmd>:answer|dtmf|hangup``),
so a retried run is exactly-once at the provider too.

The provider is used structurally (like ``workers.camera_handlers``) — no direct
SDK import. The real JTAPI / SIP ``send_dtmf`` transport is E12-05 / E13-06
(blocked); this orchestration is transport-independent and runs against
``telephony_mock``.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:  # types only — the runtime stays free of an SDK coupling
    from bbz_integration_sdk.providers import CallSnapshot, TelephonyProvider

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.door_open_commands import (
    DoorOpenCommand,
    DoorOpenOutcome,
    DoorOpenState,
)
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.repositories.door_action_profiles import (
    DoorActionProfileService,
    DoorProfileNotFoundError,
)
from bbz_core.integrations_host.providers import NoActiveProvider, active_telephony_provider
from bbz_core.logging import get_logger
from bbz_core.redaction import redacting, scrub

_log = get_logger(__name__)

_ENDPOINT = "POST /api/v1/doors/{endpoint_id}/open"
_DEFAULT_TIMEOUT_S = 15
_POLL_INTERVAL_S = 0.1

#: normalized ``CallLifecycleState`` values (bbz_integration_sdk) — matched as
#: strings so this module stays SDK-import-free, like ``workers.camera_handlers``.
_SEND_DTMF_CAPABILITY = "call.send_dtmf"
_STATE_CONNECTED = "connected"
_RINGING_STATES = frozenset({"ringing", "offered"})
_ENDED_STATES = frozenset({"disconnected", "failed"})


class DoorOpenError(RuntimeError):
    """The request cannot be processed at all (bad endpoint). Maps to 4xx."""

    def __init__(self, message: str, *, code: str = "door_open_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DoorOpenResult:
    command_id: uuid.UUID
    endpoint_id: uuid.UUID
    outcome: str
    opened: bool
    detail: str

    def as_body(self) -> dict[str, str | bool]:
        return {
            "command_id": str(self.command_id),
            "endpoint_id": str(self.endpoint_id),
            "outcome": self.outcome,
            "opened": self.opened,
            "detail": self.detail,
        }

    @classmethod
    def from_body(cls, body: dict[str, object] | None) -> DoorOpenResult:
        b = body or {}
        return cls(
            command_id=uuid.UUID(str(b["command_id"])),
            endpoint_id=uuid.UUID(str(b["endpoint_id"])),
            outcome=str(b["outcome"]),
            opened=bool(b["opened"]),
            detail=str(b.get("detail") or ""),
        )


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


_TERMINAL_STATE = {
    DoorOpenOutcome.OPENED.value: DoorOpenState.DONE.value,
    DoorOpenOutcome.MEDIA_TIMEOUT.value: DoorOpenState.TIMED_OUT.value,
}


class DoorOpenService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def open(
        self,
        *,
        endpoint_id: uuid.UUID,
        call_id: str,
        command_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        may_answer: bool = True,
    ) -> DoorOpenResult:
        """``may_answer`` — whether the caller holds ``door.answer`` (the API
        resolves it; a ringing call that needs answering without it →
        ``answer_forbidden``). Defaults to ``True`` for direct/service callers."""
        rhash = request_hash({"endpoint_id": str(endpoint_id), "call_id": call_id})
        async with idempotent(
            self._s,
            command_id=command_id,
            endpoint=_ENDPOINT,
            request_hash=rhash,
            user_id=actor_id,
        ) as slot:
            if slot.replay is not None:
                return DoorOpenResult.from_body(slot.replay.body)

            await self._s.rollback()
            endpoint = await self._s.get(TechnicalEndpoint, endpoint_id)
            if endpoint is None or endpoint.type != "door_station":
                raise DoorOpenError("not a door station", code="not_found")
            profile_id: uuid.UUID | None = endpoint.dtmf_profile_id
            timeout_s = endpoint.door_open_timeout_seconds or _DEFAULT_TIMEOUT_S

            # Resolve the DTMF sequence up front and transiently. A missing key is
            # a 503 before anything is created (``DoorSecretsNotConfigured``
            # propagates); a dangling profile ref degrades to ``no_profile``.
            digits: str | None = None
            delay_ms, auto_hangup = 0, True
            if profile_id is not None:
                try:
                    digits, delay_ms, auto_hangup = await DoorActionProfileService(
                        self._s
                    ).resolve_dtmf(profile_id)
                except DoorProfileNotFoundError:
                    digits = None

            # Claim the state-machine row. ``on_conflict_do_nothing`` makes this
            # safe for a concurrent duplicate and for a retry after the durable
            # command row was purged: a prior attempt's row is picked up and
            # either replayed (terminal) or resumed (``_drive`` is idempotent).
            await self._s.rollback()
            async with self._s.begin():
                claimed = (
                    await self._s.execute(
                        pg_insert(DoorOpenCommand)
                        .values(
                            command_id=command_id,
                            endpoint_id=endpoint_id,
                            profile_id=profile_id,
                            call_id=call_id,
                            state=DoorOpenState.REQUESTED.value,
                            requested_by=actor_id,
                        )
                        .on_conflict_do_nothing(index_elements=["command_id"])
                        .returning(DoorOpenCommand.id)
                    )
                ).scalar_one_or_none()
                if claimed is not None:
                    cmd_pk = claimed
                    prior_outcome, prior_detail = None, ""
                    await self._audit(
                        AuditAction.DOOR_OPEN_REQUESTED,
                        actor_id,
                        endpoint_id,
                        {
                            "command_id": str(command_id),
                            "door_action_profile_id": str(profile_id) if profile_id else None,
                            "call_id": call_id,
                        },
                    )
                else:
                    prior = (
                        await self._s.execute(
                            select(DoorOpenCommand).where(DoorOpenCommand.command_id == command_id)
                        )
                    ).scalar_one()
                    cmd_pk = prior.id
                    prior_outcome = prior.outcome
                    prior_detail = prior.detail or ""

            if prior_outcome is not None:
                del digits  # a prior attempt already finished — drop the plaintext
                result = DoorOpenResult(
                    command_id=command_id,
                    endpoint_id=endpoint_id,
                    outcome=prior_outcome,
                    opened=prior_outcome == DoorOpenOutcome.OPENED.value,
                    detail=prior_detail,
                )
                slot.set_result(200, result.as_body())
                return result

            if digits is None:
                outcome, detail = (
                    DoorOpenOutcome.NO_PROFILE.value,
                    "the door station has no usable DTMF profile",
                )
            else:
                # E17-06: register the sequence so every sink (audit, event,
                # outbox, structured log) masks it — a provider that echoes the
                # code in an error can't leak it past this block.
                with redacting(digits):
                    outcome, detail = await self._drive(
                        cmd_pk,
                        command_id=command_id,
                        call_id=call_id,
                        digits=digits,
                        delay_ms=delay_ms,
                        auto_hangup=auto_hangup,
                        timeout_s=timeout_s,
                        may_answer=may_answer,
                    )
                    detail = scrub(detail)  # mask before it spreads to the row / result
            del digits  # drop the plaintext as soon as the flow is done

            await self._s.rollback()
            async with self._s.begin():
                fresh = await self._s.get(DoorOpenCommand, cmd_pk)
                assert fresh is not None
                fresh.outcome = outcome
                fresh.detail = detail
                fresh.state = _TERMINAL_STATE.get(outcome, DoorOpenState.FAILED.value)
                fresh.completed_at = _now()
                await self._audit(
                    AuditAction.DOOR_OPEN_RESULT,
                    actor_id,
                    endpoint_id,
                    {
                        "command_id": str(command_id),
                        "door_action_profile_id": str(profile_id) if profile_id else None,
                        "call_id": call_id,
                        "outcome": outcome,
                        "detail": detail,
                    },
                )

            result = DoorOpenResult(
                command_id=command_id,
                endpoint_id=endpoint_id,
                outcome=outcome,
                opened=outcome == DoorOpenOutcome.OPENED.value,
                detail=detail,
            )
            slot.set_result(200, result.as_body())
            return result

    # --- the state machine -------------------------------------------------

    async def _drive(
        self,
        cmd_pk: uuid.UUID,
        *,
        command_id: uuid.UUID,
        call_id: str,
        digits: str,
        delay_ms: int,
        auto_hangup: bool,
        timeout_s: int,
        may_answer: bool,
    ) -> tuple[str, str]:
        try:
            provider = await active_telephony_provider()
        except NoActiveProvider:
            return DoorOpenOutcome.TELEPHONY_UNAVAILABLE.value, "no active telephony provider"

        if not provider.capabilities().has(_SEND_DTMF_CAPABILITY):
            return (
                DoorOpenOutcome.NO_DTMF_CAPABILITY.value,
                "the telephony provider cannot send DTMF",
            )

        try:
            snap = await self._snapshot(provider, call_id)
            if snap is None:
                return DoorOpenOutcome.CALLER_GONE.value, "no active call for the given call_id"

            if str(snap.state) in _RINGING_STATES:
                if not may_answer:
                    return (
                        DoorOpenOutcome.ANSWER_FORBIDDEN.value,
                        "the doorbell call must be answered first — needs door.answer",
                    )
                await self._set_state(cmd_pk, DoorOpenState.ANSWERING)
                await provider.answer(call_id=call_id, command_id=f"door:{command_id}:answer")

            await self._set_state(cmd_pk, DoorOpenState.CONNECTING)
            connected = await self._await_connected(provider, call_id, timeout_s)
            if connected is None:
                return DoorOpenOutcome.CALLER_GONE.value, "the call ended before media was ready"
            if not connected:
                return (
                    DoorOpenOutcome.MEDIA_TIMEOUT.value,
                    f"the call did not reach CONNECTED within {timeout_s}s",
                )

            await self._s.rollback()
            async with self._s.begin():
                row = await self._s.get(DoorOpenCommand, cmd_pk)
                assert row is not None
                already_sent = row.dtmf_sent_at is not None
            if not already_sent:
                await provider.send_dtmf(
                    call_id=call_id, dtmf=digits, command_id=f"door:{command_id}:dtmf"
                )
                await self._s.rollback()
                async with self._s.begin():
                    row = await self._s.get(DoorOpenCommand, cmd_pk)
                    assert row is not None
                    row.dtmf_sent_at = _now()
                    row.state = DoorOpenState.DTMF_SENT.value
        except Exception as exc:  # a provider fault before the DTMF: the door did not open
            _log.warning("door_open_provider_error", call_id=call_id, error=repr(exc))
            return DoorOpenOutcome.PROVIDER_ERROR.value, f"telephony provider error: {exc!s}"

        # the DTMF is out — the door has opened. The post-delay + hangup are
        # best-effort cleanup and never downgrade the outcome.
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
        if auto_hangup:
            try:
                await self._set_state(cmd_pk, DoorOpenState.COMPLETING)
                await provider.hangup(call_id=call_id, command_id=f"door:{command_id}:hangup")
            except Exception as exc:  # cleanup only — the door already opened
                _log.warning("door_open_hangup_failed", call_id=call_id, error=repr(exc))
                return DoorOpenOutcome.OPENED.value, "DTMF delivered; auto-hangup failed"

        return DoorOpenOutcome.OPENED.value, "DTMF sequence delivered"

    async def _snapshot(self, provider: TelephonyProvider, call_id: str) -> CallSnapshot | None:
        for snap in await provider.get_active_calls():
            if snap.call_id == call_id:
                return snap
        return None

    async def _await_connected(
        self, provider: TelephonyProvider, call_id: str, timeout_s: int
    ) -> bool | None:
        """``True`` connected, ``False`` timed out, ``None`` the call ended."""
        deadline = _now() + _dt.timedelta(seconds=timeout_s)
        while True:
            snap = await self._snapshot(provider, call_id)
            if snap is None:
                return None
            state = str(snap.state)
            if state == _STATE_CONNECTED:
                return True
            if state in _ENDED_STATES:
                return None
            if _now() >= deadline:
                return False
            await asyncio.sleep(_POLL_INTERVAL_S)

    async def _set_state(self, cmd_pk: uuid.UUID, state: DoorOpenState) -> None:
        await self._s.rollback()
        async with self._s.begin():
            row = await self._s.get(DoorOpenCommand, cmd_pk)
            assert row is not None
            row.state = state.value

    async def _audit(
        self,
        action: AuditAction,
        actor_id: uuid.UUID | None,
        endpoint_id: uuid.UUID,
        after: dict[str, object],
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="technical_endpoint",
            target_id=str(endpoint_id),
            after=after,
        )
