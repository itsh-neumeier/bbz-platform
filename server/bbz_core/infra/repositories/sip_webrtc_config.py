"""Per-operator WebRTC SIP endpoint config + PJSIP generation (roadmap E13-11).

ADR-0035. Each operator who may take calls in the browser gets a WebRTC SIP
endpoint on BBZ's Asterisk. This service is the CRUD + the pure PJSIP renderer
(``[transport-wss]`` + per-operator ``type=endpoint`` / ``auth`` / ``aor``),
which the admin ``asterisk-config`` export concatenates after the trunk config.

The SIP password is a secret: stored only as ``auth_password_ciphertext``
(Fernet, ``BBZ_SIP_ENCRYPTION_KEY`` via :mod:`bbz_core.infra.sip_secrets`),
never returned by the admin API, logged, or written to an audit row. It is
disclosed once — over TLS, to the operator's own session — by
:meth:`SipWebrtcConfigService.credentials_for`
(``GET /api/v1/telephony/webrtc-credentials``).
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.audit.service import changed_fields
from bbz_core.infra.models.identity import User
from bbz_core.infra.models.sip_gateway import SIP_WEBRTC_CONTEXT, SipWebrtcEndpoint
from bbz_core.infra.sip_secrets import decrypt_webrtc_password, encrypt_webrtc_password
from bbz_core.settings import get_settings

#: opus first (WebRTC default), then G.711 for the trunk side
_WEBRTC_CODECS = "opus,ulaw,alaw"


class SipWebrtcError(ValueError):
    """A field value is not acceptable. The message never echoes a password."""


class SipWebrtcNotFoundError(SipWebrtcError):
    pass


class SipWebrtcNotConfigured(SipWebrtcError):
    """No WebRTC WSS URL is configured (``BBZ_SIP_WEBRTC_WS_URL``) — the
    softphone cannot be offered."""


@dataclass(frozen=True)
class SipWebrtcEndpointView:
    user_id: uuid.UUID
    auth_username: str
    #: whether a SIP password is stored — never the password itself
    auth_password_configured: bool
    enabled: bool


@dataclass(frozen=True)
class SipWebrtcCredentials:
    """Everything the operator's JsSIP client needs. ``auth_password`` is
    cleartext — return over TLS only, never log or audit it."""

    ws_url: str
    sip_uri: str
    auth_user: str
    auth_password: str
    #: RTCIceServer-shaped dicts for the browser
    ice_servers: list[dict[str, str]]


def _view(e: SipWebrtcEndpoint) -> SipWebrtcEndpointView:
    return SipWebrtcEndpointView(
        user_id=e.user_id,
        auth_username=e.auth_username,
        auth_password_configured=bool(e.auth_password_ciphertext),
        enabled=e.enabled,
    )


def _snapshot(e: SipWebrtcEndpoint) -> dict[str, object]:
    """The non-secret fields for the audit diff — never the password / ciphertext."""
    return {
        "auth_username": e.auth_username,
        "auth_password_configured": bool(e.auth_password_ciphertext),
        "enabled": e.enabled,
    }


def _audit_after(
    before: dict[str, object] | None, after: dict[str, object], *, password_set: bool
) -> dict[str, object]:
    if before is None:
        return {**after, "password_changed": password_set}
    return {
        "changed": sorted(changed_fields(before, after)),
        "password_changed": password_set,
    }


def _ice_servers(raw: str) -> list[dict[str, str]]:
    return [{"urls": u.strip()} for u in raw.split(",") if u.strip()]


class SipWebrtcConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- CRUD ------------------------------------------------------

    async def list_endpoints(self) -> list[SipWebrtcEndpointView]:
        rows = await self._s.execute(
            select(SipWebrtcEndpoint).order_by(SipWebrtcEndpoint.auth_username)
        )
        return [_view(e) for e in rows.scalars().all()]

    async def get_endpoint(self, user_id: uuid.UUID) -> SipWebrtcEndpointView | None:
        e = await self._s.get(SipWebrtcEndpoint, user_id)
        return _view(e) if e is not None else None

    async def set_endpoint(
        self,
        user_id: uuid.UUID,
        *,
        enabled: bool,
        rotate_password: bool,
        actor_id: uuid.UUID | None,
    ) -> SipWebrtcEndpointView:
        """Create the operator's endpoint (minting a username + password), or
        update ``enabled`` / rotate the password on an existing one."""
        await self._s.rollback()
        e = await self._s.get(SipWebrtcEndpoint, user_id)
        before = _snapshot(e) if e is not None else None
        password_set = False
        if e is None:
            if await self._s.get(User, user_id) is None:
                raise SipWebrtcNotFoundError(f"no such user: {user_id}")
            e = SipWebrtcEndpoint(user_id=user_id, auth_username=_mint_username())
            self._s.add(e)
            e.auth_password_ciphertext = encrypt_webrtc_password(_mint_password())
            password_set = True
        elif rotate_password:
            e.auth_password_ciphertext = encrypt_webrtc_password(_mint_password())
            password_set = True

        e.enabled = enabled
        e.updated_by = actor_id
        await self._s.flush()
        after = _snapshot(e)
        await AuditService(self._s).write(
            AuditAction.SIP_WEBRTC_ENDPOINT_CONFIGURED,
            actor_user_id=actor_id,
            target_type="sip_webrtc_endpoint",
            target_id=str(user_id),
            before=before,
            after=_audit_after(before, after, password_set=password_set),
        )
        await self._s.commit()
        view = await self.get_endpoint(user_id)
        assert view is not None
        return view

    async def delete_endpoint(self, user_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        e = await self._s.get(SipWebrtcEndpoint, user_id)
        if e is None:
            raise SipWebrtcNotFoundError(str(user_id))
        await AuditService(self._s).write(
            AuditAction.SIP_WEBRTC_ENDPOINT_REMOVED,
            actor_user_id=actor_id,
            target_type="sip_webrtc_endpoint",
            target_id=str(user_id),
            before=_snapshot(e),
        )
        await self._s.execute(delete(SipWebrtcEndpoint).where(SipWebrtcEndpoint.user_id == user_id))
        await self._s.commit()

    # --- runtime -------------------------------------------------

    async def credentials_for(self, user_id: uuid.UUID) -> SipWebrtcCredentials | None:
        """The calling operator's JsSIP credentials, or ``None`` if they have no
        enabled endpoint. Raises :class:`SipWebrtcNotConfigured` if the endpoint
        exists but no WSS URL is deployed."""
        e = await self._s.get(SipWebrtcEndpoint, user_id)
        if e is None or not e.enabled or not e.auth_password_ciphertext:
            return None
        s = get_settings()
        if not s.sip_webrtc_ws_url:
            raise SipWebrtcNotConfigured("BBZ_SIP_WEBRTC_WS_URL is not set")
        domain = _ws_host(s.sip_webrtc_ws_url)
        return SipWebrtcCredentials(
            ws_url=s.sip_webrtc_ws_url,
            sip_uri=f"sip:{e.auth_username}@{domain}",
            auth_user=e.auth_username,
            auth_password=decrypt_webrtc_password(e.auth_password_ciphertext),
            ice_servers=_ice_servers(s.sip_webrtc_ice_servers),
        )

    async def operator_endpoint_map(self) -> dict[str, str]:
        """``{str(user_id): auth_username}`` for every **enabled** endpoint — the
        adapter needs it to originate to the answering operator's WebRTC channel
        (ADR-0035 §4)."""
        rows = (await self._s.execute(select(SipWebrtcEndpoint))).scalars().all()
        return {str(e.user_id): e.auth_username for e in rows if e.enabled}

    # --- config generation (ADR-0035) --------------------------

    async def render_pjsip(self) -> str:
        """``[transport-wss]`` + a PJSIP endpoint/auth/aor per **enabled**
        operator. Decrypts the passwords in-process — the caller must stream the
        result and never persist or log it. Empty string if no endpoints."""
        rows = [
            e
            for e in (await self._s.execute(select(SipWebrtcEndpoint))).scalars().all()
            if e.enabled and e.auth_password_ciphertext
        ]
        rows.sort(key=lambda e: e.auth_username)
        if not rows:
            return ""
        s = get_settings()
        return _render_pjsip(
            rows,
            bind=s.sip_webrtc_wss_bind,
            cert_file=s.sip_webrtc_cert_file,
            priv_key_file=s.sip_webrtc_priv_key_file,
        )


def _mint_username() -> str:
    return f"op-{secrets.token_hex(4)}"


def _mint_password() -> str:
    return secrets.token_urlsafe(24)


def _ws_host(ws_url: str) -> str:
    """``wss://sip.example:8089/ws`` -> ``sip.example`` (the SIP domain)."""
    rest = ws_url.split("://", 1)[-1]
    return rest.split("/", 1)[0].split(":", 1)[0]


# --- pure renderer -----------------------------------------------

_HEADER = """\
; ============================================================================
; BBZ — generated WebRTC operator endpoints (ADR-0035). DO NOT EDIT.
; Overwritten by the BBZ sync script (deploy/sip/sync-trunk-config.sh).
; #tryinclude this from pjsip.conf. Needs a WSS-capable Asterisk (>= 16.6) and
; a TLS cert at the paths below.
; ============================================================================
"""


def _render_pjsip(
    endpoints: list[SipWebrtcEndpoint], *, bind: str, cert_file: str, priv_key_file: str
) -> str:
    out: list[str] = [
        _HEADER,
        "[transport-wss]",
        "type = transport",
        "protocol = wss",
        f"bind = {bind}",
        f"cert_file = {cert_file}",
        f"priv_key_file = {priv_key_file}",
        "",
    ]
    for e in endpoints:
        pw = decrypt_webrtc_password(e.auth_password_ciphertext)
        u = e.auth_username
        out += [
            f"; ---- operator softphone: {u} ----",
            f"[{u}]",
            "type = endpoint",
            f"context = {SIP_WEBRTC_CONTEXT}",
            "disallow = all",
            f"allow = {_WEBRTC_CODECS}",
            "webrtc = yes",
            f"auth = {u}-auth",
            f"aors = {u}-aor",
            "",
            f"[{u}-auth]",
            "type = auth",
            "auth_type = userpass",
            f"username = {u}",
            f"password = {pw}",
            "",
            f"[{u}-aor]",
            "type = aor",
            "max_contacts = 1",
            "remove_existing = yes",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"
