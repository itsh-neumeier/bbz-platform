"""Self-service TOTP enrolment for local accounts (E02-13).

    POST /auth/totp/enrol     -> secret + otpauth URI + recovery codes (once)
    POST /auth/totp/activate  -> verify a code, turn the factor on
    DELETE /auth/totp         -> turn it off

All three act on the caller's own local identity. Login then requires the
factor (``totp`` field on /auth/login; a recovery code also works).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.auth.mfa import TotpService
from bbz_core.auth.totp import TotpNotConfiguredError
from bbz_core.infra.models.identity import AuthIdentity
from bbz_core.infra.repositories.totp import TotpRepository

router = APIRouter(prefix="/auth/totp", tags=["auth"])


class EnrolOut(BaseModel):
    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class CodeIn(BaseModel):
    code: str


async def _local_identity(session: AsyncSession, user_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    row = (
        await session.execute(
            select(AuthIdentity.id, AuthIdentity.subject).where(
                AuthIdentity.user_id == user_id, AuthIdentity.provider == "local"
            )
        )
    ).first()
    if row is None:
        raise NotFoundError("no local login for this account")
    return row[0], row[1]


@router.post("/enrol", response_model=EnrolOut)
async def enrol(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> EnrolOut:
    aid, subject = await _local_identity(session, ctx.user_id)
    try:
        start = await TotpService(TotpRepository(session)).begin_enrolment(aid, account=subject)
    except TotpNotConfiguredError as exc:
        raise ValidationError("TOTP is not available on this deployment") from exc
    return EnrolOut(**start.__dict__)


@router.post("/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate(
    body: CodeIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> None:
    aid, _ = await _local_identity(session, ctx.user_id)
    if not await TotpService(TotpRepository(session)).activate(aid, body.code):
        raise ValidationError("code did not verify — enrol again and retry")
    await AuditWriter(session).record(AuditAction.MFA_ENROLLED, actor_user_id=ctx.user_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disable(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> None:
    aid, _ = await _local_identity(session, ctx.user_id)
    await TotpService(TotpRepository(session)).disable(aid)
    await AuditWriter(session).record(AuditAction.MFA_DISABLED, actor_user_id=ctx.user_id)
