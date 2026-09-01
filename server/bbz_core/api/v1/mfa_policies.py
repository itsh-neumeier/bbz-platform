"""Admin config: which roles require MFA, and self-service step-up (roadmap E21-05).

CRUD is ``permissions.manage`` (itself step-up gated, see ``api/authz.py``). Every
write is an ``MFA_POLICY_CHANGED`` audit row.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require, require_stepup
from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import NotFoundError, UnauthorizedError, ValidationError
from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.auth.mfa import ChallengeResult, TotpService
from bbz_core.infra.models.identity import AuthIdentity
from bbz_core.infra.repositories.mfa_policy import (
    MfaPolicyService,
    PolicyNotFound,
    UnknownRoleKey,
)
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.infra.repositories.totp import TotpRepository

router = APIRouter(prefix="/auth/mfa-policies", tags=["auth"])


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grace_period_days: int = Field(default=7, ge=0, le=365)


class PolicyOut(BaseModel):
    role_key: str
    grace_period_days: int


class PoliciesResponse(BaseModel):
    policies: list[PolicyOut]


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except UnknownRoleKey as exc:
        raise ValidationError(f"no such role: {exc}") from exc
    except PolicyNotFound as exc:
        raise NotFoundError("no MFA policy for that role") from exc


@router.get("", response_model=PoliciesResponse)
async def list_policies(
    _: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> PoliciesResponse:
    rows = await MfaPolicyService(session).list_policies()
    return PoliciesResponse(
        policies=[
            PolicyOut(role_key=p.role_key, grace_period_days=p.grace_period_days) for p in rows
        ]
    )


@router.put("/{role_key}", response_model=PolicyOut)
async def set_policy(
    role_key: str,
    body: PolicyIn,
    ctx: AuthContext = Depends(require_stepup("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> PolicyOut:
    with _translate():
        p = await MfaPolicyService(session).set_policy(
            role_key, grace_period_days=body.grace_period_days, actor_id=ctx.user_id
        )
    return PolicyOut(role_key=p.role_key, grace_period_days=p.grace_period_days)


@router.delete("/{role_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    role_key: str,
    ctx: AuthContext = Depends(require_stepup("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> None:
    with _translate():
        await MfaPolicyService(session).delete_policy(role_key, actor_id=ctx.user_id)


# --- self-service step-up --------------------------------------------


class StepUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    totp: str | None = None
    #: a WebAuthn assertion (from POST /auth/webauthn/authenticate/options), JSON
    webauthn: str | None = None


@router.post("/step-up", status_code=status.HTTP_204_NO_CONTENT)
async def step_up(
    body: StepUpIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> None:
    """Re-verify the caller's own second factor (TOTP / recovery code / WebAuthn)
    and mark this session fresh for step-up-gated actions (E21-05/06)."""
    if body.webauthn:
        from bbz_core.infra.repositories.webauthn import WebauthnService

        if not await WebauthnService(session).verify_authentication(
            ctx.user_id, response=body.webauthn
        ):
            await AuditWriter(session).record(
                AuditAction.MFA_CHALLENGE_FAILED, actor_user_id=ctx.user_id
            )
            raise UnauthorizedError("invalid assertion")
        await SqlAlchemySessionStore(session).mark_mfa_verified(ctx.session_id)
        return

    if not body.totp:
        raise ValidationError("a totp or webauthn value is required")
    aid = (
        await session.execute(
            select(AuthIdentity.id).where(
                AuthIdentity.user_id == ctx.user_id, AuthIdentity.provider == "local"
            )
        )
    ).scalar_one_or_none()
    if aid is None:
        raise ValidationError("no local login with MFA for this account")
    result = await TotpService(TotpRepository(session)).challenge(aid, body.totp)
    if result is ChallengeResult.BAD:
        await AuditWriter(session).record(
            AuditAction.MFA_CHALLENGE_FAILED, actor_user_id=ctx.user_id
        )
        raise UnauthorizedError("invalid code")
    if result is ChallengeResult.RECOVERY_USED:
        await AuditWriter(session).record(AuditAction.MFA_RECOVERY_USED, actor_user_id=ctx.user_id)
    await SqlAlchemySessionStore(session).mark_mfa_verified(ctx.session_id)
