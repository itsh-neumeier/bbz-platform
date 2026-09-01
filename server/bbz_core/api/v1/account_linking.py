"""Account linking + auth-provider config (roadmap E21-08).

Identity link/unlink acts on the caller's own account and needs a **fresh
second-factor confirmation** when the account has one. Provider config is
``permissions.manage``. The Admin-UI + Playwright coverage is deferred to Epic 07.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import (
    ConflictError,
    NotFoundError,
    StepUpRequiredError,
    UnauthorizedError,
    ValidationError,
)
from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.policy import PasswordPolicyError
from bbz_core.infra.models.auth_provider_config import AuthProviderConfig
from bbz_core.infra.repositories.account_linking import (
    AccountLinkingService,
    IdentityAlreadyLinked,
    IdentityNotFound,
    LastIdentityError,
    LinkingError,
    ProviderAlreadyLinked,
)
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


# --- second-factor confirmation for link/unlink ----------------------


async def _confirm_second_factor(session: AsyncSession, ctx: AuthContext) -> None:
    """If the account has a second factor, this session must have verified it
    recently (E21-08 AC: linking confirms both factors). No factor ⇒ nothing to
    confirm."""
    from bbz_core.api.v1.auth import _mfa_satisfied

    if not await _mfa_satisfied(session, ctx.user_id):
        return
    record = await SqlAlchemySessionStore(session).get_active(ctx.session_id)
    fresh = (
        record is not None
        and record.mfa_verified_at is not None
        and (_dt.datetime.now(_dt.UTC) - record.mfa_verified_at).total_seconds()
        <= get_settings().mfa_stepup_max_age_seconds
    )
    if not fresh:
        raise StepUpRequiredError(
            "confirm your second factor first (POST /auth/mfa-policies/step-up)"
        )


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, IdentityAlreadyLinked):
        return ConflictError("that identity is already linked to another account")
    if isinstance(exc, ProviderAlreadyLinked):
        return ConflictError("this account already has an identity with that provider")
    if isinstance(exc, LastIdentityError):
        return ConflictError(str(exc))
    if isinstance(exc, IdentityNotFound):
        return NotFoundError("identity not found")
    if isinstance(exc, PasswordPolicyError):
        return ValidationError(str(exc))
    if isinstance(exc, LinkingError):
        return ValidationError(str(exc))
    return exc


# --- identities -----------------------------------------------------


class IdentityOut(BaseModel):
    id: uuid.UUID
    provider: str
    subject: str
    created_at: _dt.datetime


class IdentitiesResponse(BaseModel):
    identities: list[IdentityOut]


class LocalLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class DirectoryLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


class OidcCallbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    state: str


class OidcStartOut(BaseModel):
    authorization_url: str


@router.get("/identities", response_model=IdentitiesResponse)
async def list_identities(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> IdentitiesResponse:
    rows = await AccountLinkingService(session).list_identities(ctx.user_id)
    return IdentitiesResponse(
        identities=[
            IdentityOut(id=r.id, provider=r.provider, subject=r.subject, created_at=r.created_at)
            for r in rows
        ]
    )


@router.post("/identities/local", response_model=IdentityOut, status_code=status.HTTP_201_CREATED)
async def link_local(
    body: LocalLinkIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> IdentityOut:
    await _confirm_second_factor(session, ctx)
    try:
        v = await AccountLinkingService(session).link_local(
            ctx.user_id, username=body.username, password=body.password, actor_id=ctx.user_id
        )
    except (LinkingError, PasswordPolicyError) as exc:
        raise _translate(exc) from exc
    return IdentityOut(id=v.id, provider=v.provider, subject=v.subject, created_at=v.created_at)


@router.post("/identities/ldap", response_model=IdentityOut, status_code=status.HTTP_201_CREATED)
async def link_ldap(
    body: DirectoryLinkIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> IdentityOut:
    await _confirm_second_factor(session, ctx)
    import asyncio

    from bbz_core.auth.ldap import LdapClient, LdapError
    from bbz_core.infra.repositories.ldap_login import config_from_settings

    try:
        principal = await asyncio.to_thread(
            LdapClient(config_from_settings()).authenticate, body.username, body.password
        )
    except LdapError as exc:
        raise UnauthorizedError("directory authentication failed") from exc
    try:
        v = await AccountLinkingService(session).link_external(
            ctx.user_id, provider="ldap_ad", subject=principal.uid, actor_id=ctx.user_id
        )
    except LinkingError as exc:
        raise _translate(exc) from exc
    return IdentityOut(id=v.id, provider=v.provider, subject=v.subject, created_at=v.created_at)


@router.post("/identities/oidc/{provider}/start", response_model=OidcStartOut)
async def link_oidc_start(
    provider: str,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> OidcStartOut:
    await _confirm_second_factor(session, ctx)
    from bbz_core.api.v1.auth import _translate_oidc
    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    with _translate_oidc():
        url = await OidcLoginService(session).begin(provider, link_user_id=ctx.user_id)
    return OidcStartOut(authorization_url=url)


@router.post("/identities/oidc/{provider}/callback", status_code=status.HTTP_204_NO_CONTENT)
async def link_oidc_callback(
    provider: str,
    body: OidcCallbackIn,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> Response:
    from bbz_core.api.v1.auth import _translate_oidc
    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    with _translate_oidc():
        link_user_id, subject = await OidcLoginService(session).complete_link(
            provider, code=body.code, state=body.state
        )
    if link_user_id != ctx.user_id:
        raise UnauthorizedError("this linking flow belongs to another account")
    try:
        await AccountLinkingService(session).link_external(
            ctx.user_id, provider=provider, subject=subject, actor_id=ctx.user_id
        )
    except LinkingError as exc:
        raise _translate(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/identities/{identity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_identity(
    identity_id: uuid.UUID,
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> Response:
    await _confirm_second_factor(session, ctx)
    try:
        await AccountLinkingService(session).unlink(ctx.user_id, identity_id, actor_id=ctx.user_id)
    except (LinkingError, IdentityNotFound) as exc:
        raise _translate(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- provider config (permissions.manage) -------------------------


class ProviderConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    display_name: str = Field(default="", max_length=80)


class ProviderConfigOut(BaseModel):
    provider: str
    enabled: bool
    display_name: str
    #: whether the deployment's env / secrets actually back this provider
    env_configured: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderConfigOut]


_KNOWN_PROVIDERS = ("local", "entra_oidc", "ldap_ad")


def _env_configured(name: str) -> bool:
    if name == "local":
        return True
    s = get_settings()
    if name == "entra_oidc":
        return bool(s.oidc_entra_issuer and s.oidc_entra_client_id)
    if name == "ldap_ad":
        return bool(s.ldap_url and s.ldap_bind_dn)
    return False


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers(
    _: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> ProvidersResponse:
    rows = {c.provider: c for c in (await session.execute(select(AuthProviderConfig))).scalars()}
    out = []
    for name in _KNOWN_PROVIDERS:
        cfg = rows.get(name)
        out.append(
            ProviderConfigOut(
                provider=name,
                enabled=cfg.enabled if cfg else True,
                display_name=cfg.display_name if cfg else "",
                env_configured=_env_configured(name),
            )
        )
    return ProvidersResponse(providers=out)


@router.put("/providers/{provider}", response_model=ProviderConfigOut)
async def set_provider_config(
    provider: str,
    body: ProviderConfigIn,
    ctx: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> ProviderConfigOut:
    if provider not in _KNOWN_PROVIDERS:
        raise ValidationError(f"unknown provider: {provider}")
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    await session.rollback()
    async with session.begin():
        await session.execute(
            pg_insert(AuthProviderConfig)
            .values(
                provider=provider,
                enabled=body.enabled,
                display_name=body.display_name,
                updated_by=ctx.user_id,
            )
            .on_conflict_do_update(
                index_elements=["provider"],
                set_={
                    "enabled": body.enabled,
                    "display_name": body.display_name,
                    "updated_by": ctx.user_id,
                    "updated_at": _dt.datetime.now(_dt.UTC),
                },
            )
        )
        await AuditService(session).write(
            AuditAction.AUTH_PROVIDER_CONFIGURED,
            actor_user_id=ctx.user_id,
            target_type="auth_provider",
            target_id=provider,
            after={"enabled": body.enabled, "display_name": body.display_name},
        )
    return ProviderConfigOut(
        provider=provider,
        enabled=body.enabled,
        display_name=body.display_name,
        env_configured=_env_configured(provider),
    )
