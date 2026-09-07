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

from fastapi import APIRouter, Depends, status
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
from bbz_core.infra.sip_secrets import SipSecretsNotConfigured
from bbz_core.integrations_host.providers import (
    NoActiveProvider,
    evict_telephony_provider,
    probe_telephony_sip,
)

router = APIRouter(prefix="/admin/telephony/sip", tags=["admin"])

_DTMF_TRANSPORTS = ("rfc2833", "sip_info")


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except SipLineNotFoundError as exc:
        raise NotFoundError("SIP line not found") from exc
    except SipConfigError as exc:
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
