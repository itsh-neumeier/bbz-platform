"""Call control API (roadmap E11-06).

Permission-gated, idempotent endpoints that translate an operator action into a
call on the **active** telephony provider (``telephony_mock`` today; a real CTI
gateway in Epic 12). Every attempt is audited (``CALL_CONTROL_ACTION``) with the
action and the provider's acknowledgement. A repeated ``X-Command-Id`` replays
the stored response and never re-hits the provider — no double "answer".
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.telephony import Call
from bbz_core.integrations_host.providers import NoActiveProvider, active_telephony_provider

router = APIRouter(prefix="/calls", tags=["calls"])

_ProviderCall = Callable[[object, str, str], Awaitable[object]]


class DialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1)
    destination: str = Field(min_length=1)


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(min_length=1)


class ControlOut(BaseModel):
    call_id: uuid.UUID | None
    action: str
    accepted: bool
    detail: str | None = None


def _ack_fields(ack: object) -> tuple[bool, str | None, str | None]:
    accepted = bool(getattr(ack, "accepted", True))
    detail = getattr(ack, "detail", None)
    provider_call_id = getattr(ack, "call_id", None)
    return accepted, detail, provider_call_id


async def _provider() -> object:
    try:
        return await active_telephony_provider()
    except NoActiveProvider as exc:
        raise ConflictError(f"telephony is not available: {exc}") from exc


async def _control(
    *,
    call_id: uuid.UUID,
    action: str,
    invoke: _ProviderCall,
    ctx: AuthContext,
    env: CommandEnvelope,
    session: AsyncSession,
) -> ControlOut:
    rhash = request_hash({"call_id": str(call_id), "action": action})
    async with idempotent(
        session,
        command_id=env.command_id,
        endpoint=f"POST /api/v1/calls/{{id}}/{action}",
        request_hash=rhash,
        user_id=ctx.user_id,
    ) as slot:
        if slot.replay is not None:
            return ControlOut.model_validate(slot.replay.body)

        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("call not found")
        if not call.source_call_id:
            raise ConflictError("the provider has not assigned this call an id yet")
        source_call_id, bbz_call_id = call.source_call_id, call.bbz_call_id

        provider = await _provider()
        ack = await invoke(provider, source_call_id, str(env.command_id))
        accepted, detail, _ = _ack_fields(ack)

        await session.rollback()
        async with session.begin():
            await AuditService(session).write(
                AuditAction.CALL_CONTROL_ACTION,
                actor_user_id=ctx.user_id,
                target_type="call",
                target_id=str(call_id),
                after={
                    "action": action,
                    "bbz_call_id": bbz_call_id,
                    "accepted": accepted,
                    "detail": detail,
                },
            )
        out = ControlOut(call_id=call_id, action=action, accepted=accepted, detail=detail)
        slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
        return out


@router.post("/{call_id}/answer", response_model=ControlOut)
async def answer_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.answer")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="answer",
        invoke=lambda p, scid, cid: p.answer(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/hangup", response_model=ControlOut)
async def hangup_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hangup")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="hangup",
        invoke=lambda p, scid, cid: p.hangup(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/hold", response_model=ControlOut)
async def hold_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hold")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="hold",
        invoke=lambda p, scid, cid: p.hold(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/resume", response_model=ControlOut)
async def resume_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hold")),  # resume shares the hold permission
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="resume",
        invoke=lambda p, scid, cid: p.resume(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/transfer", response_model=ControlOut)
async def transfer_call(
    call_id: uuid.UUID,
    body: TransferIn,
    ctx: AuthContext = Depends(require("calls.transfer")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    dest = body.destination
    return await _control(
        call_id=call_id,
        action="transfer",
        invoke=lambda p, scid, cid: p.transfer(call_id=scid, destination=dest, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


class DialOut(BaseModel):
    action: str = "dial"
    accepted: bool
    detail: str | None = None


@router.post("/dial", response_model=DialOut)
async def dial(
    body: DialIn,
    ctx: AuthContext = Depends(require("calls.dial")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> DialOut:
    """Start an outbound call. The ``calls`` row appears once the provider's
    ``CALL_RINGING`` event is ingested (E11-03/04)."""
    rhash = request_hash({"line_id": body.line_id, "destination": body.destination})
    async with idempotent(
        session,
        command_id=env.command_id,
        endpoint="POST /api/v1/calls/dial",
        request_hash=rhash,
        user_id=ctx.user_id,
    ) as slot:
        if slot.replay is not None:
            return DialOut.model_validate(slot.replay.body)

        provider = await _provider()
        ack = await provider.dial(  # type: ignore[attr-defined]
            line_id=body.line_id, destination=body.destination, command_id=str(env.command_id)
        )
        accepted, detail, _ = _ack_fields(ack)
        await session.rollback()
        async with session.begin():
            await AuditService(session).write(
                AuditAction.CALL_CONTROL_ACTION,
                actor_user_id=ctx.user_id,
                target_type="call",
                after={
                    "action": "dial",
                    "line_id": body.line_id,
                    "destination": body.destination,
                    "accepted": accepted,
                },
            )
        out = DialOut(accepted=accepted, detail=detail)
        slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
        return out
