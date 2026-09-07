"""SIP trunk (ITSP) config + Asterisk config generation (roadmap E13-09).

ADR-0034. BBZ stores the SIP trunk (LEONET / Telekom / …) and its public
numbers; :meth:`SipTrunkConfigService.render_asterisk_config` renders the PJSIP
+ dialplan text a sync script drops onto the Asterisk box. The trunk auth
password is a secret: stored only as ``auth_password_ciphertext`` (Fernet,
``BBZ_SIP_ENCRYPTION_KEY`` via :mod:`bbz_core.infra.sip_secrets`), never returned
by the API, logged, or written to an audit row — reads report
``auth_password_configured``.

:meth:`render_asterisk_config` decrypts the passwords in-process to build the
cleartext PJSIP ``type=auth`` sections; the caller must stream the result and
never persist or log it.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.audit.service import changed_fields
from bbz_core.infra.models.sip_gateway import (
    SIP_TRUNK_DTMF_MODES,
    SIP_TRUNK_PROVIDERS,
    SIP_TRUNK_TRANSPORTS,
    SipNumber,
    SipTrunk,
)
from bbz_core.infra.sip_secrets import decrypt_trunk_password, encrypt_trunk_password

_TRUNK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")
_CODECS = re.compile(r"^[a-z0-9]+(,[a-z0-9]+)*$")
_LINE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_PORT_RANGE = range(1, 65536)


class SipTrunkError(ValueError):
    """A field value is not acceptable. The message never echoes a password."""


class SipTrunkNotFoundError(SipTrunkError):
    pass


class SipNumberNotFoundError(SipTrunkError):
    pass


@dataclass(frozen=True)
class SipTrunkView:
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
    #: whether a trunk auth password is stored — never the password itself
    auth_password_configured: bool
    match_hosts: str
    codecs: str
    dtmf_mode: str
    caller_id_e164: str


@dataclass(frozen=True)
class SipNumberView:
    e164: str
    trunk_id: str
    bbz_line_id: str
    label: str
    registration: bool
    auth_username: str
    auth_password_configured: bool
    enabled: bool


@dataclass(frozen=True)
class RenderedTrunkConfig:
    #: ``pjsip.conf`` fragment — CONTAINS cleartext trunk passwords, never persist it
    pjsip: str
    #: ``extensions.conf`` fragment — inbound DID -> ``Stasis(bbz-sip, …)``
    extensions: str


def _trunk_view(t: SipTrunk) -> SipTrunkView:
    return SipTrunkView(
        trunk_id=t.trunk_id,
        provider=t.provider,
        display_name=t.display_name,
        enabled=t.enabled,
        sip_server=t.sip_server,
        sip_port=t.sip_port,
        transport=t.transport,
        outbound_proxy=t.outbound_proxy,
        from_domain=t.from_domain,
        registration=t.registration,
        auth_username=t.auth_username,
        auth_password_configured=bool(t.auth_password_ciphertext),
        match_hosts=t.match_hosts,
        codecs=t.codecs,
        dtmf_mode=t.dtmf_mode,
        caller_id_e164=t.caller_id_e164,
    )


def _number_view(n: SipNumber) -> SipNumberView:
    return SipNumberView(
        e164=n.e164,
        trunk_id=n.trunk_id,
        bbz_line_id=n.bbz_line_id,
        label=n.label,
        registration=n.registration,
        auth_username=n.auth_username,
        auth_password_configured=bool(n.auth_password_ciphertext),
        enabled=n.enabled,
    )


def _trunk_snapshot(t: SipTrunk) -> dict[str, object]:
    """The non-secret fields for the audit diff — never the password / ciphertext."""
    return {
        "provider": t.provider,
        "display_name": t.display_name,
        "enabled": t.enabled,
        "sip_server": t.sip_server,
        "sip_port": t.sip_port,
        "transport": t.transport,
        "outbound_proxy": t.outbound_proxy,
        "from_domain": t.from_domain,
        "registration": t.registration,
        "auth_username": t.auth_username,
        "auth_password_configured": bool(t.auth_password_ciphertext),
        "match_hosts": t.match_hosts,
        "codecs": t.codecs,
        "dtmf_mode": t.dtmf_mode,
        "caller_id_e164": t.caller_id_e164,
    }


def _number_snapshot(n: SipNumber) -> dict[str, object]:
    return {
        "trunk_id": n.trunk_id,
        "bbz_line_id": n.bbz_line_id,
        "label": n.label,
        "registration": n.registration,
        "auth_username": n.auth_username,
        "auth_password_configured": bool(n.auth_password_ciphertext),
        "enabled": n.enabled,
    }


def _audit_after(
    before: dict[str, object] | None, after: dict[str, object], *, password_set: bool
) -> dict[str, object]:
    """Full snapshot on create, a ``{"changed": [...]}`` field list on update —
    plus ``password_changed`` either way. Never carries the password itself."""
    if before is None:
        return {**after, "password_changed": password_set}
    return {
        "changed": sorted(changed_fields(before, after)),
        "password_changed": password_set,
    }


def _validate_match_hosts(raw: str) -> str:
    """Comma / whitespace separated hosts or CIDRs -> a normalised comma list.
    A bare host passes through; an IP/CIDR is validated."""
    parts = [p.strip() for p in re.split(r"[,\s]+", raw or "") if p.strip()]
    for part in parts:
        if "/" in part or _looks_like_ip(part):
            try:
                ipaddress.ip_network(part, strict=False)
            except ValueError as exc:
                raise SipTrunkError(f"match host {part!r} is not a valid IP / CIDR") from exc
    return ",".join(parts)


def _looks_like_ip(value: str) -> bool:
    head = value.split("/", 1)[0]
    try:
        ipaddress.ip_address(head)
    except ValueError:
        return False
    return True


class SipTrunkConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- trunks ------------------------------------------------------

    async def list_trunks(self) -> list[SipTrunkView]:
        rows = await self._s.execute(select(SipTrunk).order_by(SipTrunk.trunk_id))
        return [_trunk_view(t) for t in rows.scalars().all()]

    async def get_trunk(self, trunk_id: str) -> SipTrunkView | None:
        t = await self._s.get(SipTrunk, trunk_id)
        return _trunk_view(t) if t is not None else None

    async def set_trunk(
        self,
        trunk_id: str,
        *,
        provider: str,
        display_name: str,
        enabled: bool,
        sip_server: str,
        sip_port: int,
        transport: str,
        outbound_proxy: str,
        from_domain: str,
        registration: bool,
        auth_username: str,
        auth_password: str | None,
        match_hosts: str,
        codecs: str,
        dtmf_mode: str,
        caller_id_e164: str,
        actor_id: uuid.UUID | None,
    ) -> SipTrunkView:
        tid = trunk_id.strip().lower()
        if not _TRUNK_ID.match(tid):
            raise SipTrunkError("trunk_id must be a slug: lowercase letters, digits, '-'")
        if provider not in SIP_TRUNK_PROVIDERS:
            raise SipTrunkError(f"provider must be one of {sorted(SIP_TRUNK_PROVIDERS)}")
        if transport not in SIP_TRUNK_TRANSPORTS:
            raise SipTrunkError(f"transport must be one of {sorted(SIP_TRUNK_TRANSPORTS)}")
        if dtmf_mode not in SIP_TRUNK_DTMF_MODES:
            raise SipTrunkError(f"dtmf_mode must be one of {sorted(SIP_TRUNK_DTMF_MODES)}")
        if sip_port not in _PORT_RANGE:
            raise SipTrunkError("sip_port must be 1-65535")
        codecs_n = (codecs or "").strip().lower().replace(" ", "")
        if not _CODECS.match(codecs_n):
            raise SipTrunkError("codecs must be a comma list of codec names, e.g. 'alaw,ulaw'")
        if caller_id_e164 and not _E164.match(caller_id_e164):
            raise SipTrunkError("caller_id_e164 must be E.164, e.g. +49891234567")
        match_n = _validate_match_hosts(match_hosts)
        if enabled and not sip_server.strip():
            raise SipTrunkError("sip_server is required to enable a trunk")

        await self._s.rollback()
        t = await self._s.get(SipTrunk, tid)
        before = _trunk_snapshot(t) if t is not None else None
        if t is None:
            t = SipTrunk(trunk_id=tid)
            self._s.add(t)

        t.provider = provider
        t.display_name = display_name.strip()
        t.enabled = enabled
        t.sip_server = sip_server.strip()
        t.sip_port = sip_port
        t.transport = transport
        t.outbound_proxy = outbound_proxy.strip()
        t.from_domain = from_domain.strip() or sip_server.strip()
        t.registration = registration
        t.auth_username = auth_username.strip()
        t.match_hosts = match_n
        t.codecs = codecs_n
        t.dtmf_mode = dtmf_mode
        t.caller_id_e164 = caller_id_e164.strip()
        t.updated_by = actor_id
        password_set = False
        if auth_password:
            t.auth_password_ciphertext = encrypt_trunk_password(auth_password)
            password_set = True
        if registration and not t.auth_username:
            raise SipTrunkError("auth_username is required when the trunk registers")
        if registration and not t.auth_password_ciphertext:
            raise SipTrunkError("a password is required when the trunk registers")

        await self._s.flush()
        after = _trunk_snapshot(t)
        await AuditService(self._s).write(
            AuditAction.SIP_TRUNK_CONFIGURED,
            actor_user_id=actor_id,
            target_type="sip_trunk",
            target_id=tid,
            before=before,
            after=_audit_after(before, after, password_set=password_set),
        )
        await self._s.commit()
        view = await self.get_trunk(tid)
        assert view is not None
        return view

    async def delete_trunk(self, trunk_id: str, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        t = await self._s.get(SipTrunk, trunk_id)
        if t is None:
            raise SipTrunkNotFoundError(trunk_id)
        await AuditService(self._s).write(
            AuditAction.SIP_TRUNK_REMOVED,
            actor_user_id=actor_id,
            target_type="sip_trunk",
            target_id=trunk_id,
            before=_trunk_snapshot(t),
        )
        # sip_numbers cascades via the FK
        await self._s.execute(delete(SipTrunk).where(SipTrunk.trunk_id == trunk_id))
        await self._s.commit()

    # --- numbers ---------------------------------------------------

    async def list_numbers(self, *, trunk_id: str | None = None) -> list[SipNumberView]:
        stmt = select(SipNumber).order_by(SipNumber.e164)
        if trunk_id is not None:
            stmt = stmt.where(SipNumber.trunk_id == trunk_id)
        rows = await self._s.execute(stmt)
        return [_number_view(n) for n in rows.scalars().all()]

    async def set_number(
        self,
        e164: str,
        *,
        trunk_id: str,
        bbz_line_id: str,
        label: str,
        registration: bool,
        auth_username: str,
        auth_password: str | None,
        enabled: bool,
        actor_id: uuid.UUID | None,
    ) -> SipNumberView:
        num = e164.strip()
        if not _E164.match(num):
            raise SipTrunkError("number must be E.164, e.g. +49891234567")
        line_id = bbz_line_id.strip()
        if line_id and not _LINE_ID.match(line_id):
            raise SipTrunkError("bbz_line_id: letters, digits, '.', '_', '-' only")

        await self._s.rollback()
        if await self._s.get(SipTrunk, trunk_id) is None:
            raise SipTrunkNotFoundError(trunk_id)
        n = await self._s.get(SipNumber, num)
        before = _number_snapshot(n) if n is not None else None
        if n is None:
            n = SipNumber(e164=num)
            self._s.add(n)

        n.trunk_id = trunk_id
        n.bbz_line_id = line_id
        n.label = label.strip()
        n.registration = registration
        n.auth_username = auth_username.strip()
        n.enabled = enabled
        password_set = False
        if auth_password:
            n.auth_password_ciphertext = encrypt_trunk_password(auth_password)
            password_set = True
        if registration and not (n.auth_username and n.auth_password_ciphertext):
            raise SipTrunkError(
                "auth_username and a password are required when the number registers"
            )

        await self._s.flush()
        after = _number_snapshot(n)
        await AuditService(self._s).write(
            AuditAction.SIP_NUMBER_CONFIGURED,
            actor_user_id=actor_id,
            target_type="sip_number",
            target_id=num,
            before=before,
            after=_audit_after(before, after, password_set=password_set),
        )
        await self._s.commit()
        views = await self.list_numbers()
        return next(v for v in views if v.e164 == num)

    async def delete_number(self, e164: str, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        n = await self._s.get(SipNumber, e164.strip())
        if n is None:
            raise SipNumberNotFoundError(e164)
        await AuditService(self._s).write(
            AuditAction.SIP_NUMBER_REMOVED,
            actor_user_id=actor_id,
            target_type="sip_number",
            target_id=e164.strip(),
            before=_number_snapshot(n),
        )
        await self._s.execute(delete(SipNumber).where(SipNumber.e164 == e164.strip()))
        await self._s.commit()

    # --- config generation (ADR-0034) ----------------------------

    async def render_asterisk_config(self) -> RenderedTrunkConfig:
        """Render the ``#tryinclude`` PJSIP + dialplan fragments for every
        **enabled** trunk. Decrypts the auth passwords in-process — the caller
        must stream the result and never persist or log it."""
        trunks = [t for t in (await self._s.execute(select(SipTrunk))).scalars().all() if t.enabled]
        trunks.sort(key=lambda t: t.trunk_id)
        numbers = [
            n for n in (await self._s.execute(select(SipNumber))).scalars().all() if n.enabled
        ]
        by_trunk: dict[str, list[SipNumber]] = {}
        for n in sorted(numbers, key=lambda n: n.e164):
            by_trunk.setdefault(n.trunk_id, []).append(n)
        return RenderedTrunkConfig(
            pjsip=_render_pjsip(trunks, by_trunk),
            extensions=_render_extensions(trunks, by_trunk),
        )


# --- pure renderers -------------------------------------------------

_PJSIP_HEADER = """\
; ============================================================================
; BBZ — generated SIP trunk config (ADR-0034). DO NOT EDIT.
; Overwritten by the BBZ sync script (deploy/sip/sync-trunk-config.sh).
; #tryinclude this from pjsip.conf. Endpoints reference transport-udp /
; transport-tcp / transport-tls — define those in your pjsip.conf (Asterisk's
; stock transport names).
; ============================================================================
"""

_EXTEN_HEADER = """\
; ============================================================================
; BBZ — generated SIP trunk dialplan (ADR-0034). DO NOT EDIT.
; #tryinclude this from extensions.conf. Each [from-<trunk>] context normalises
; the inbound DID and hands the call to Stasis(bbz-sip, <line>); BBZ drives it
; over ARI from there.
; ============================================================================
"""


def _digits(e164: str) -> str:
    return re.sub(r"\D+", "", e164)


def _transport_ref(transport: str) -> str:
    return f"transport-{transport}"


def _contact_uri(trunk: SipTrunk) -> str:
    return f"sip:{trunk.sip_server}:{trunk.sip_port}"


def _render_pjsip(trunks: list[SipTrunk], by_trunk: dict[str, list[SipNumber]]) -> str:
    out: list[str] = [_PJSIP_HEADER]
    for t in trunks:
        tref = _transport_ref(t.transport)
        out.append(f"; ---- trunk: {t.trunk_id} ({t.display_name or t.provider}) ----")
        out += [
            f"[{t.trunk_id}-auth]",
            "type = auth",
            "auth_type = userpass",
            f"username = {t.auth_username}",
            f"password = {decrypt_trunk_password(t.auth_password_ciphertext)}"
            if t.auth_password_ciphertext
            else "password = ",
            "",
            f"[{t.trunk_id}-aor]",
            "type = aor",
            f"contact = {_contact_uri(t)}",
            "qualify_frequency = 60",
            "",
        ]
        if t.registration:
            out += [
                f"[{t.trunk_id}-reg]",
                "type = registration",
                f"transport = {tref}",
                f"outbound_auth = {t.trunk_id}-auth",
                f"server_uri = {_contact_uri(t)}",
                f"client_uri = sip:{t.auth_username}@{t.from_domain or t.sip_server}",
                f"contact_user = {t.auth_username}",
                "retry_interval = 60",
                "forbidden_retry_interval = 300",
                "expiration = 300",
                "line = yes",
                f"endpoint = {t.trunk_id}",
            ]
            if t.outbound_proxy:
                out.append(f"outbound_proxy = {t.outbound_proxy}")
            out.append("")
        hosts = [h for h in t.match_hosts.split(",") if h]
        if hosts:
            out.append(f"[{t.trunk_id}-identify]")
            out.append("type = identify")
            out.append(f"endpoint = {t.trunk_id}")
            out += [f"match = {h}" for h in hosts]
            out.append("")
        out += [
            f"[{t.trunk_id}]",
            "type = endpoint",
            f"transport = {tref}",
            f"context = from-{t.trunk_id}",
            "disallow = all",
            f"allow = {t.codecs}",
            f"outbound_auth = {t.trunk_id}-auth",
            f"aors = {t.trunk_id}-aor",
            f"from_user = {t.auth_username}",
            f"from_domain = {t.from_domain or t.sip_server}",
            f"dtmf_mode = {t.dtmf_mode}",
            "direct_media = no",
            "rtp_symmetric = yes",
            "force_rport = yes",
            "rewrite_contact = yes",
            "trust_id_inbound = yes",
        ]
        if t.outbound_proxy:
            out.append(f"outbound_proxy = {t.outbound_proxy}")
        out.append("")
        for n in by_trunk.get(t.trunk_id, []):
            if not (n.registration and n.auth_username and n.auth_password_ciphertext):
                continue
            base = f"{t.trunk_id}-n-{_digits(n.e164)}"
            out += [
                f"; number {n.e164}"
                + (f" ({n.label})" if n.label else "")
                + " — per-MSN registration",
                f"[{base}-auth]",
                "type = auth",
                "auth_type = userpass",
                f"username = {n.auth_username}",
                f"password = {decrypt_trunk_password(n.auth_password_ciphertext)}",
                "",
                f"[{base}-reg]",
                "type = registration",
                f"transport = {tref}",
                f"outbound_auth = {base}-auth",
                f"server_uri = {_contact_uri(t)}",
                f"client_uri = sip:{n.auth_username}@{t.from_domain or t.sip_server}",
                f"contact_user = {n.auth_username}",
                "retry_interval = 60",
                "forbidden_retry_interval = 300",
                "expiration = 300",
                "line = yes",
                f"endpoint = {t.trunk_id}",
            ]
            if t.outbound_proxy:
                out.append(f"outbound_proxy = {t.outbound_proxy}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _stasis_arg(n: SipNumber) -> str:
    return n.bbz_line_id or n.e164


def _render_extensions(trunks: list[SipTrunk], by_trunk: dict[str, list[SipNumber]]) -> str:
    out: list[str] = [_EXTEN_HEADER]
    for t in trunks:
        out.append(f"[from-{t.trunk_id}]")
        out += [
            "exten => _[+0-9a-zA-Z].,1,"
            f"NoOp(BBZ trunk {t.trunk_id} inbound: ${{EXTEN}} <- ${{CALLERID(num)}})",
            " same => n,Set(SIPCALLID=${CHANNEL(pjsip,call-id)})",
            " same => n,Set(BBZ_LINE=${EXTEN})",
        ]
        for n in by_trunk.get(t.trunk_id, []):
            arg = _stasis_arg(n)
            digits = _digits(n.e164)
            # match the DID as sent E.164 (+49…), national (0049… / 49…) or bare
            for form in (n.e164, digits, f"0{digits[2:]}" if digits.startswith("49") else digits):
                out.append(f' same => n,ExecIf($["${{EXTEN}}"="{form}"]?Set(BBZ_LINE={arg}))')
        out += [
            " same => n,Stasis(bbz-sip,${BBZ_LINE})",
            " same => n,Hangup()",
            "exten => h,1,NoOp(BBZ trunk hangup ${CHANNEL})",
            "",
        ]

    # a minimal outbound context — BBZ's dial verb originates PJSIP/<line>
    # directly today; choosing a trunk + CLI for outbound is a follow-up (ADR-0034).
    default_trunk = next((t for t in trunks if t.caller_id_e164), trunks[0] if trunks else None)
    if default_trunk is not None:
        out += [
            "[bbz-trunk-out]",
            f"; fallback outbound via {default_trunk.trunk_id} — see ADR-0034",
            f"exten => _[+0-9].,1,Dial(PJSIP/${{EXTEN}}@{default_trunk.trunk_id},60)",
            " same => n,Hangup()",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"
