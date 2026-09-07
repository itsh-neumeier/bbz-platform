"""Admin: the SIP (Asterisk / ARI) gateway config (roadmap E13-07, ADR-0033).

The `telephony_sip` connection lives in the DB and is managed from here — host,
port, TLS, the Stasis app, the ARI user, the SIP lines, and a "test connection"
probe. The ARI **password** enters only in a ``PUT`` body over TLS, is encrypted
immediately (``BBZ_SIP_ENCRYPTION_KEY``), and is **never** returned by ``GET``,
logged, or written to an audit row — ``GET`` reports ``ari_password_configured``.

Every route needs ``integrations.configure``. A successful ``PUT`` evicts the
cached provider so the change takes effect without a restart. If
``telephony_sip`` is the active provider but the encryption key is unset, writes
and the probe return 503 (fail-closed).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ServiceUnavailableError, ValidationError
from bbz_core.infra.repositories.sip_config import (
    SipConfigError,
    SipConfigService,
    SipGatewayView,
    SipLineNotFoundError,
    SipLineView,
)
from bbz_core.infra.repositories.sip_trunk_config import (
    SipNumberNotFoundError,
    SipNumberView,
    SipTrunkConfigService,
    SipTrunkError,
    SipTrunkNotFoundError,
    SipTrunkView,
)
from bbz_core.infra.sip_secrets import SipSecretsNotConfigured
from bbz_core.integrations_host.providers import (
    NoActiveProvider,
    evict_telephony_provider,
    probe_sip_trunk,
    probe_telephony_sip,
)

router = APIRouter(prefix="/admin/telephony/sip", tags=["admin"])

_DTMF_TRANSPORTS = ("rfc2833", "sip_info")


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except (SipLineNotFoundError, SipTrunkNotFoundError, SipNumberNotFoundError) as exc:
        raise NotFoundError(str(exc) or "not found") from exc
    except (SipConfigError, SipTrunkError) as exc:
        raise ValidationError(str(exc)) from exc
    except SipSecretsNotConfigured as exc:
        raise ServiceUnavailableError(
            "SIP encryption key (BBZ_SIP_ENCRYPTION_KEY) is not set"
        ) from exc


class GatewayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(max_length=255)
    port: int = Field(default=8088, ge=1, le=65535)
    tls: bool = True
    app_name: str = Field(default="bbz-sip", min_length=1, max_length=80)
    dtmf_transport: str = Field(default="rfc2833", pattern="^(rfc2833|sip_info)$")
    ari_username: str = Field(default="", max_length=120)
    #: write-only — omit to keep the stored password, "" to keep it, a value to replace it
    ari_password: str | None = Field(default=None, max_length=255)
    enabled: bool = False


class GatewayOut(BaseModel):
    instance_id: str
    kind: str
    host: str
    port: int
    tls: bool
    app_name: str
    dtmf_transport: str
    ari_username: str
    ari_password_configured: bool
    enabled: bool
    created_at: _dt.datetime | None
    updated_at: _dt.datetime | None


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asterisk_endpoint: str | None = Field(default=None, max_length=255)
    label: str = Field(default="", max_length=120)
    enabled: bool = True


class LineOut(BaseModel):
    bbz_line_id: str
    asterisk_endpoint: str
    label: str
    enabled: bool


class SipConfigOut(BaseModel):
    gateway: GatewayOut
    lines: list[LineOut]
    #: whether `telephony_sip` is the selected telephony provider
    active: bool


class ProbeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: probe an unsaved gateway; omit the body entirely to probe the stored one
    host: str = Field(max_length=255)
    port: int = Field(default=8088, ge=1, le=65535)
    tls: bool = True
    app_name: str = Field(default="bbz-sip", max_length=80)
    ari_username: str = Field(default="", max_length=120)
    ari_password: str = Field(default="", max_length=255)


class ProbeOut(BaseModel):
    reachable: bool
    detail: str
    asterisk_version: str | None = None


def _gw_out(v: SipGatewayView) -> GatewayOut:
    return GatewayOut(
        instance_id=v.instance_id,
        kind=v.kind,
        host=v.host,
        port=v.port,
        tls=v.tls,
        app_name=v.app_name,
        dtmf_transport=v.dtmf_transport,
        ari_username=v.ari_username,
        ari_password_configured=v.ari_password_configured,
        enabled=v.enabled,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _line_out(v: SipLineView) -> LineOut:
    return LineOut(
        bbz_line_id=v.bbz_line_id,
        asterisk_endpoint=v.asterisk_endpoint,
        label=v.label,
        enabled=v.enabled,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> SipConfigService:
    return SipConfigService(session)


def _sip_is_active() -> bool:
    from bbz_core.settings import get_settings

    return get_settings().telephony_integration_id == "telephony_sip"


@router.get("", response_model=SipConfigOut)
async def get_sip_config(
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipConfigService = Depends(_svc),
) -> SipConfigOut:
    return SipConfigOut(
        gateway=_gw_out(await svc.get()),
        lines=[_line_out(v) for v in await svc.list_lines()],
        active=_sip_is_active(),
    )


@router.put("", response_model=SipConfigOut)
async def put_sip_config(
    body: GatewayIn,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipConfigService = Depends(_svc),
) -> SipConfigOut:
    with _translate():
        gw = await svc.set(
            host=body.host,
            port=body.port,
            tls=body.tls,
            app_name=body.app_name,
            dtmf_transport=body.dtmf_transport,
            ari_username=body.ari_username,
            ari_password=body.ari_password,
            enabled=body.enabled,
            actor_id=ctx.user_id,
        )
    await evict_telephony_provider()
    return SipConfigOut(
        gateway=_gw_out(gw),
        lines=[_line_out(v) for v in await svc.list_lines()],
        active=_sip_is_active(),
    )


@router.put("/lines/{bbz_line_id}", response_model=LineOut)
async def put_sip_line(
    bbz_line_id: str,
    body: LineIn,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipConfigService = Depends(_svc),
) -> LineOut:
    with _translate():
        line = await svc.set_line(
            bbz_line_id,
            asterisk_endpoint=body.asterisk_endpoint,
            label=body.label,
            enabled=body.enabled,
            actor_id=ctx.user_id,
        )
    await evict_telephony_provider()
    return _line_out(line)


@router.delete("/lines/{bbz_line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sip_line(
    bbz_line_id: str,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipConfigService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete_line(bbz_line_id, actor_id=ctx.user_id)
    await evict_telephony_provider()


@router.post("/test", response_model=ProbeOut)
async def test_sip_connection(
    body: ProbeIn | None = None,
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipConfigService = Depends(_svc),
) -> ProbeOut:
    config: dict[str, Any] | None
    if body is not None:
        config = {
            "gateway": {
                "kind": "asterisk_ari",
                "host": body.host,
                "port": body.port,
                "tls": body.tls,
            },
            "app_name": body.app_name,
            "credentials": {"username": body.ari_username, "password": body.ari_password},
        }
    else:
        with _translate():
            config = await svc.runtime_config(for_probe=True)
        if config is None:
            raise ValidationError("no SIP gateway host is configured to test")
    try:
        reachable, detail, version = await probe_telephony_sip(config)
    except NoActiveProvider as exc:  # pragma: no cover - manifest missing
        raise ServiceUnavailableError("the telephony_sip adapter is not available") from exc
    return ProbeOut(reachable=reachable, detail=detail, asterisk_version=version)


# ======================================================================
# SIP trunks (ITSP) + public numbers — ADR-0034 (E13-09)
# ======================================================================


class TrunkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(default="generic", pattern="^(leonet|telekom|generic)$")
    display_name: str = Field(default="", max_length=120)
    enabled: bool = False
    sip_server: str = Field(default="", max_length=255)
    sip_port: int = Field(default=5060, ge=1, le=65535)
    transport: str = Field(default="udp", pattern="^(udp|tcp|tls)$")
    outbound_proxy: str = Field(default="", max_length=255)
    from_domain: str = Field(default="", max_length=255)
    #: emit a PJSIP ``type=registration`` (BBZ registers to the ITSP)
    registration: bool = True
    auth_username: str = Field(default="", max_length=255)
    #: write-only — omit / "" keeps the stored password, a value replaces it
    auth_password: str | None = Field(default=None, max_length=255)
    match_hosts: str = Field(default="", max_length=2000)
    codecs: str = Field(default="alaw,ulaw", max_length=255)
    dtmf_mode: str = Field(default="rfc4733", pattern="^(rfc4733|inband|info|auto)$")
    caller_id_e164: str = Field(default="", max_length=20)


class TrunkOut(BaseModel):
    trunk_id: str
    provider: str
    display_name: str
    enabled: bool
    sip_server: str
    sip_port: int
    transport: str
    outbound_proxy: str
    from_domain: str
    registration: bool
    auth_username: str
    auth_password_configured: bool
    match_hosts: str
    codecs: str
    dtmf_mode: str
    caller_id_e164: str


class NumberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trunk_id: str = Field(max_length=64)
    bbz_line_id: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=120)
    #: per-number registration (the LEONET per-MSN model) — needs its own auth
    registration: bool = False
    auth_username: str = Field(default="", max_length=255)
    auth_password: str | None = Field(default=None, max_length=255)
    enabled: bool = True


class NumberOut(BaseModel):
    e164: str
    trunk_id: str
    bbz_line_id: str
    label: str
    registration: bool
    auth_username: str
    auth_password_configured: bool
    enabled: bool


class TrunksOut(BaseModel):
    trunks: list[TrunkOut]
    numbers: list[NumberOut]


class TrunkProbeOut(BaseModel):
    #: online | loaded | not_loaded | unreachable — "loaded" = the config is on
    #: the box but the endpoint has no active contact (normal for an inbound-only
    #: or not-yet-registered trunk; ARI can't report REGISTER state)
    state: str
    detail: str


def _trunk_out(v: SipTrunkView) -> TrunkOut:
    return TrunkOut(**v.__dict__)


def _number_out(v: SipNumberView) -> NumberOut:
    return NumberOut(**v.__dict__)


def _trunk_svc(session: AsyncSession = Depends(db_session)) -> SipTrunkConfigService:
    return SipTrunkConfigService(session)


@router.get("/trunks", response_model=TrunksOut)
async def list_sip_trunks(
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> TrunksOut:
    return TrunksOut(
        trunks=[_trunk_out(v) for v in await svc.list_trunks()],
        numbers=[_number_out(v) for v in await svc.list_numbers()],
    )


@router.put("/trunks/{trunk_id}", response_model=TrunkOut)
async def put_sip_trunk(
    trunk_id: str,
    body: TrunkIn,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> TrunkOut:
    with _translate():
        trunk = await svc.set_trunk(
            trunk_id,
            provider=body.provider,
            display_name=body.display_name,
            enabled=body.enabled,
            sip_server=body.sip_server,
            sip_port=body.sip_port,
            transport=body.transport,
            outbound_proxy=body.outbound_proxy,
            from_domain=body.from_domain,
            registration=body.registration,
            auth_username=body.auth_username,
            auth_password=body.auth_password,
            match_hosts=body.match_hosts,
            codecs=body.codecs,
            dtmf_mode=body.dtmf_mode,
            caller_id_e164=body.caller_id_e164,
            actor_id=ctx.user_id,
        )
    return _trunk_out(trunk)


@router.delete("/trunks/{trunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sip_trunk(
    trunk_id: str,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> None:
    with _translate():
        await svc.delete_trunk(trunk_id, actor_id=ctx.user_id)


@router.put("/numbers/{e164}", response_model=NumberOut)
async def put_sip_number(
    e164: str,
    body: NumberIn,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> NumberOut:
    with _translate():
        number = await svc.set_number(
            e164,
            trunk_id=body.trunk_id,
            bbz_line_id=body.bbz_line_id,
            label=body.label,
            registration=body.registration,
            auth_username=body.auth_username,
            auth_password=body.auth_password,
            enabled=body.enabled,
            actor_id=ctx.user_id,
        )
    return _number_out(number)


@router.delete("/numbers/{e164}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sip_number(
    e164: str,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> None:
    with _translate():
        await svc.delete_number(e164, actor_id=ctx.user_id)


@router.get("/asterisk-config")
async def get_asterisk_config(
    part: str = Query(default="all", pattern="^(all|pjsip|extensions)$"),
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> Response:
    """The generated PJSIP + dialplan text for the sync script / a copy-paste
    (ADR-0034). **Contains the trunk auth passwords in cleartext** — the
    response is ``no-store`` and BBZ never writes this to disk, logs it, or
    audits it."""
    with _translate():
        rendered = await svc.render_asterisk_config()
    if part == "pjsip":
        body = rendered.pjsip
    elif part == "extensions":
        body = rendered.extensions
    else:
        body = (
            "; == pjsip.conf ==\n"
            + rendered.pjsip
            + "\n; == extensions.conf ==\n"
            + rendered.extensions
        )
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/trunks/{trunk_id}/test", response_model=TrunkProbeOut)
async def test_sip_trunk(
    trunk_id: str,
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipTrunkConfigService = Depends(_trunk_svc),
) -> TrunkProbeOut:
    if await svc.get_trunk(trunk_id) is None:
        raise NotFoundError(f"SIP trunk {trunk_id!r} not found")
    try:
        state, detail = await probe_sip_trunk(trunk_id)
    except NoActiveProvider as exc:  # pragma: no cover - manifest missing
        raise ServiceUnavailableError("the telephony_sip adapter is not available") from exc
    return TrunkProbeOut(state=state, detail=detail)
