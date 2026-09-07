"""SIP gateway config: read / write the DB-backed Asterisk connection (E13-07).

ADR-0033. The ARI password enters once (a ``PUT`` body over TLS), is encrypted
immediately, and is never returned, logged, or audited — ``get`` reports only
``ari_password_configured``. Every write emits a ``SIP_GATEWAY_CONFIGURED`` /
``SIP_LINE_*`` audit row with a redacted non-secret before/after diff.

:meth:`runtime_config` decrypts the password in-process to build the shape
``integrations.telephony_sip.adapter.build`` expects — only
``active_telephony_provider()`` calls it, and it must not log the result.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.audit.service import changed_fields
from bbz_core.infra.models.sip_gateway import (
    SIP_DTMF_TRANSPORTS,
    SIP_GATEWAY_KINDS,
    SipGateway,
    SipLine,
)
from bbz_core.infra.sip_secrets import decrypt_ari_password, encrypt_ari_password

_INSTANCE = "sip"
_PORT_RANGE = range(1, 65536)


class SipConfigError(ValueError):
    """A field value is not acceptable. The message never echoes the password."""


class SipLineNotFoundError(SipConfigError):
    pass


@dataclass(frozen=True)
class SipGatewayView:
    instance_id: str
    kind: str
    host: str
    port: int
    tls: bool
    app_name: str
    dtmf_transport: str
    ari_username: str
    #: whether an ARI password is stored — never the password itself
    ari_password_configured: bool
    enabled: bool
    updated_by: uuid.UUID | None
    created_at: Any
    updated_at: Any


@dataclass(frozen=True)
class SipLineView:
    bbz_line_id: str
    asterisk_endpoint: str
    label: str
    enabled: bool


_DEFAULT = SipGatewayView(
    instance_id=_INSTANCE,
    kind="asterisk_ari",
    host="",
    port=8088,
    tls=True,
    app_name="bbz-sip",
    dtmf_transport="rfc2833",
    ari_username="",
    ari_password_configured=False,
    enabled=False,
    updated_by=None,
    created_at=None,
    updated_at=None,
)


def _gw_view(g: SipGateway) -> SipGatewayView:
    return SipGatewayView(
        instance_id=g.instance_id,
        kind=g.kind,
        host=g.host,
        port=g.port,
        tls=g.tls,
        app_name=g.app_name,
        dtmf_transport=g.dtmf_transport,
        ari_username=g.ari_username,
        ari_password_configured=bool(g.ari_password_ciphertext),
        enabled=g.enabled,
        updated_by=g.updated_by,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


def _line_view(line: SipLine) -> SipLineView:
    return SipLineView(
        bbz_line_id=line.bbz_line_id,
        asterisk_endpoint=line.asterisk_endpoint,
        label=line.label,
        enabled=line.enabled,
    )


def _non_secret_snapshot(g: SipGateway) -> dict[str, Any]:
    return {
        "host": g.host,
        "port": g.port,
        "tls": g.tls,
        "app_name": g.app_name,
        "dtmf_transport": g.dtmf_transport,
        "ari_username": g.ari_username,
        "enabled": g.enabled,
        "ari_password_configured": bool(g.ari_password_ciphertext),
    }


class SipConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- gateway ------------------------------------------------------

    async def get(self) -> SipGatewayView:
        g = await self._row()
        return _gw_view(g) if g is not None else _DEFAULT

    async def set(
        self,
        *,
        host: str,
        port: int,
        tls: bool,
        app_name: str,
        dtmf_transport: str,
        ari_username: str,
        ari_password: str | None,
        enabled: bool,
        actor_id: uuid.UUID | None,
    ) -> SipGatewayView:
        if dtmf_transport not in SIP_DTMF_TRANSPORTS:
            raise SipConfigError(f"dtmf_transport must be one of {sorted(SIP_DTMF_TRANSPORTS)}")
        if port not in _PORT_RANGE:
            raise SipConfigError("port must be 1-65535")
        if not app_name.strip():
            raise SipConfigError("app_name must not be empty")
        if enabled and not host.strip():
            raise SipConfigError("host is required to enable the gateway")

        await self._s.rollback()
        g, created = await self._ensure_gateway()
        before = None if created else _non_secret_snapshot(g)

        g.host = host.strip()
        g.port = port
        g.tls = tls
        g.app_name = app_name.strip()
        g.dtmf_transport = dtmf_transport
        g.ari_username = ari_username.strip()
        g.enabled = enabled
        g.updated_by = actor_id
        password_set = False
        if ari_password is not None and ari_password != "":
            g.ari_password_ciphertext = encrypt_ari_password(ari_password)
            password_set = True

        await self._s.flush()
        after = _non_secret_snapshot(g)
        await AuditService(self._s).write(
            AuditAction.SIP_GATEWAY_CONFIGURED,
            actor_user_id=actor_id,
            target_type="sip_gateway",
            target_id=_INSTANCE,
            before=before,
            after={**after, "password_changed": password_set},
        )
        await self._s.commit()
        return await self.get()

    # --- lines -------------------------------------------------------

    async def list_lines(self) -> list[SipLineView]:
        result = await self._s.execute(select(SipLine).order_by(SipLine.bbz_line_id))
        return [_line_view(line) for line in result.scalars().all()]

    async def set_line(
        self,
        bbz_line_id: str,
        *,
        asterisk_endpoint: str | None,
        label: str,
        enabled: bool,
        actor_id: uuid.UUID | None,
    ) -> SipLineView:
        line_id = bbz_line_id.strip()
        if not line_id:
            raise SipConfigError("bbz_line_id must not be empty")
        endpoint = (asterisk_endpoint or "").strip() or f"PJSIP/{line_id}"

        await self._s.rollback()
        await self._ensure_gateway()  # the FK target must exist
        line = await self._s.get(SipLine, line_id)
        before: dict[str, Any] | None
        if line is None:
            before = None
            line = SipLine(bbz_line_id=line_id, gateway_instance_id=_INSTANCE)
            self._s.add(line)
        else:
            before = {
                "asterisk_endpoint": line.asterisk_endpoint,
                "label": line.label,
                "enabled": line.enabled,
            }
        line.asterisk_endpoint = endpoint
        line.label = label.strip()
        line.enabled = enabled

        await self._s.flush()
        after = {"asterisk_endpoint": endpoint, "label": line.label, "enabled": enabled}
        await AuditService(self._s).write(
            AuditAction.SIP_LINE_CONFIGURED,
            actor_user_id=actor_id,
            target_type="sip_line",
            target_id=line_id,
            before=before,
            after={"changed": sorted(changed_fields(before, after))} if before else after,
        )
        await self._s.commit()
        return _line_view(line)

    async def delete_line(self, bbz_line_id: str, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        line = await self._s.get(SipLine, bbz_line_id)
        if line is None:
            raise SipLineNotFoundError(bbz_line_id)
        await AuditService(self._s).write(
            AuditAction.SIP_LINE_REMOVED,
            actor_user_id=actor_id,
            target_type="sip_line",
            target_id=bbz_line_id,
            before={"asterisk_endpoint": line.asterisk_endpoint},
        )
        await self._s.execute(delete(SipLine).where(SipLine.bbz_line_id == bbz_line_id))
        await self._s.commit()

    # --- runtime ---------------------------------------------------

    async def runtime_config(self) -> dict[str, Any] | None:
        """The ``config_schema.json``-shaped dict for
        ``integrations.telephony_sip.adapter.build`` — or ``None`` when the
        gateway is disabled / unconfigured (the provider then stays a scaffold).
        Decrypts the ARI password in-process; the caller must not log this."""
        g = await self._row()
        if g is None or not g.enabled or not g.host:
            return None
        lines = await self.list_lines()
        creds: dict[str, str] = {"username": g.ari_username}
        if g.ari_password_ciphertext:
            creds["password"] = decrypt_ari_password(g.ari_password_ciphertext)
        return {
            "gateway": {"kind": g.kind, "host": g.host, "port": g.port, "tls": g.tls},
            "app_name": g.app_name,
            "credentials": creds,
            "dtmf_transport": g.dtmf_transport,
            "lines": [line.bbz_line_id for line in lines if line.enabled],
            "line_endpoints": {
                line.bbz_line_id: line.asterisk_endpoint for line in lines if line.enabled
            },
        }

    # --- internals ------------------------------------------------

    async def _ensure_gateway(self) -> tuple[SipGateway, bool]:
        """The single ``sip`` gateway row, created (disabled) if absent. The
        migration seeds it in a provisioned DB; tests build the schema with
        ``create_all`` and rely on this."""
        g = await self._row()
        if g is not None:
            return g, False
        g = SipGateway(instance_id=_INSTANCE, kind=SIP_GATEWAY_KINDS[0])
        self._s.add(g)
        await self._s.flush()
        return g, True

    async def _row(self) -> SipGateway | None:
        return (
            await self._s.execute(
                select(SipGateway)
                .where(SipGateway.instance_id == _INSTANCE)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
