"""Asterisk ARI event → normalized :class:`CallEvent` mapping (roadmap E13-04,
MASTER_PROMPT §8.4).

ARI channel-lifecycle events become ``telephony_event.v1`` items; only
allow-listed fields cross the edge — ARI channel ids and vendor detail are
dropped except for a diagnostic ``channel_id`` in ``metadata``. The stable
``source_call_id`` is the **SIP Call-ID** when the dialplan exposes it as the
``SIPCALLID`` channel variable, else the ARI channel id (still stable per call).
"""

from __future__ import annotations

import datetime as _dt
import uuid

from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent as _E
from bbz_integration_sdk.providers.telephony_types import CallEvent

_STASIS_END = frozenset({"StasisEnd", "ChannelHangupRequest", "ChannelDestroyed"})


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _ts(raw: object) -> _dt.datetime:
    if isinstance(raw, str):
        try:
            return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return _now()


def _call_id(channel: dict[str, object]) -> str | None:
    cv = channel.get("channelvars")
    if isinstance(cv, dict) and cv.get("SIPCALLID"):
        return str(cv["SIPCALLID"])
    cid = channel.get("id")
    return str(cid) if cid else None


def _party(channel: dict[str, object], key: str) -> str | None:
    party = channel.get(key)
    if isinstance(party, dict) and party.get("number"):
        return str(party["number"])
    return None


def _caller_name(channel: dict[str, object]) -> str | None:
    caller = channel.get("caller")
    if isinstance(caller, dict) and caller.get("name"):
        return str(caller["name"])
    return None


def _dialplan_exten(channel: dict[str, object]) -> str | None:
    dp = channel.get("dialplan")
    if isinstance(dp, dict) and dp.get("exten"):
        return str(dp["exten"])
    return None


def map_ari_event(raw: dict[str, object], *, provider: str, gateway_node: str) -> CallEvent | None:
    """One ARI event → a :class:`CallEvent`, or ``None`` for events we don't
    surface (playback/recording/variable-set/…)."""
    kind = str(raw.get("type") or "")
    channel = raw.get("channel")
    channel = channel if isinstance(channel, dict) else {}

    def _ev(
        event_type: _E, *, device_id: str | None = None, meta_extra: dict[str, object] | None = None
    ) -> CallEvent:
        meta: dict[str, object] = {}
        if channel.get("id"):
            meta["channel_id"] = channel["id"]
        if meta_extra:
            meta.update(meta_extra)
        return CallEvent(
            telephony_event_id=f"sip-{uuid.uuid4()}",
            provider=provider,
            event_type=event_type,
            raw_event_type=kind or "unknown",
            source_call_id=_call_id(channel),
            line_id=str(channel.get("name")) if channel.get("name") else None,
            device_id=device_id,
            calling_number=_party(channel, "caller"),
            called_number=_dialplan_exten(channel) or _party(channel, "connected"),
            display_name=_caller_name(channel),
            occurred_at=_ts(raw.get("timestamp")),
            received_at=_now(),
            gateway_node=gateway_node,
            metadata=meta,
        )

    if kind == "StasisStart":
        return _ev(_E.CALL_RINGING, meta_extra={"direction": "inbound"})
    if kind == "ChannelStateChange":
        state = str(channel.get("state") or "")
        if state == "Up":
            return _ev(_E.CALL_ANSWERED)
        if state in ("Ring", "Ringing"):
            return _ev(_E.CALL_RINGING)
        return None
    if kind == "ChannelHold":
        return _ev(_E.CALL_HELD)
    if kind == "ChannelUnhold":
        return _ev(_E.CALL_RESUMED)
    if kind in _STASIS_END:
        return _ev(_E.CALL_DISCONNECTED)
    if kind == "PeerStatusChange":
        peer = raw.get("peer")
        peer = peer if isinstance(peer, dict) else {}
        status = str(peer.get("peer_status") or "")
        device = str(peer.get("peer_id")) if peer.get("peer_id") else None
        if status == "Reachable":
            return _ev(_E.DEVICE_REGISTERED, device_id=device)
        if status == "Unreachable":
            return _ev(_E.DEVICE_UNREGISTERED, device_id=device)
        return None
    return None
