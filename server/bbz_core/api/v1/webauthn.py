"""Self-service WebAuthn / FIDO2 credentials for local accounts (roadmap E21-06).

    POST /auth/webauthn/register/options   -> PublicKeyCredentialCreationOptions
    POST /auth/webauthn/register/verify    -> store the credential
    GET  /auth/webauthn/credentials         -> list this account's credentials
    DELETE /auth/webauthn/credentials/{id}  -> remove one
    POST /auth/webauthn/authenticate/options -> options for a step-up / re-auth

Login uses the credential as a second factor via the ``webauthn`` field on
``/auth/login`` (see the ``webauthn_required`` response there).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import NotFoundError, ServiceUnavailableError, ValidationError
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.repositories.webauthn import (
    CredentialNotFound,
    WebauthnError,
    WebauthnNotConfigured,
    WebauthnService,
)

router = APIRouter(prefix="/auth/webauthn", tags=["auth"])


class OptionsOut(BaseModel):
    #: the raw PublicKeyCredential{Creation,Request}Options JSON for the browser
    options: str


class RegisterVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str  # the navigator.credentials.create() result, JSON-serialised
    name: str = Field(default="security key", max_length=80)


class CredentialOut(BaseModel):
    id: uuid.UUID
    name: str
    aaguid: str
    transports: list[str]
    created_at: object
    last_used_at: object | None


class CredentialsOut(BaseModel):
    credentials: list[CredentialOut]


async def _local(session: AsyncSession, user_id: uuid.UUID) -> tuple[uuid.UUID, str, str]:
    row = (
        await session.execute(
            select(AuthIdentity.id, AuthIdentity.subject, User.display_name)
            .join(User, User.id == AuthIdentity.user_id)
            .where(AuthIdentity.user_id == user_id, AuthIdentity.provider == "local")
        )
    ).first()
    if row is None:
        raise NotFoundError("no local login for this account")
    return row[0], row[1], row[2]


@router.post("/register/options", response_model=OptionsOut)
async def register_options(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> OptionsOut:
    aid, subject, display_name = await _local(session, ctx.user_id)
    try:
        opts = await WebauthnService(session).begin_registration(
            aid, user_name=subject, user_display_name=display_name
        )
    except WebauthnNotConfigured as exc:
        raise ServiceUnavailableError("WebAuthn is not configured on this deployment") from exc
    return OptionsOut(options=opts)


@router.post("/register/verify", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
async def register_verify(
    body: RegisterVerifyIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> CredentialOut:
    aid, _, _ = await _local(session, ctx.user_id)
    try:
        cred = await WebauthnService(session).complete_registration(
            aid, response=body.response, name=body.name, actor_id=ctx.user_id
        )
    except WebauthnNotConfigured as exc:
        raise ServiceUnavailableError("WebAuthn is not configured on this deployment") from exc
    except WebauthnError as exc:
        raise ValidationError(str(exc)) from exc
    return CredentialOut(**cred.__dict__)


@router.get("/credentials", response_model=CredentialsOut)
async def list_credentials(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> CredentialsOut:
    aid, _, _ = await _local(session, ctx.user_id)
    rows = await WebauthnService(session).list_credentials(aid)
    return CredentialsOut(credentials=[CredentialOut(**r.__dict__) for r in rows])


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_credential(
    credential_id: uuid.UUID,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> Response:
    aid, _, _ = await _local(session, ctx.user_id)
    try:
        await WebauthnService(session).remove_credential(
            credential_id, auth_identity_id=aid, actor_id=ctx.user_id
        )
    except CredentialNotFound as exc:
        raise NotFoundError("credential not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/authenticate/options", response_model=OptionsOut)
async def authenticate_options(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> OptionsOut:
    """Options for a step-up / re-auth of the already-logged-in user."""
    try:
        opts = await WebauthnService(session).begin_authentication(ctx.user_id)
    except WebauthnNotConfigured as exc:
        raise ServiceUnavailableError("WebAuthn is not configured on this deployment") from exc
    except CredentialNotFound as exc:
        raise NotFoundError("no WebAuthn credential for this account") from exc
    return OptionsOut(options=opts)
