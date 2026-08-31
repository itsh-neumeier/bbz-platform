"""Normalized capability model.

An integration advertises which normalized operations it supports. The core
never assumes a capability is present — it feature-detects (MASTER_PROMPT §8.12).
Capability *names* are BBZ-defined and vendor-neutral.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Capability(StrEnum):
    # telephony (MASTER_PROMPT §8.12)
    CALL_ANSWER = "call.answer"
    CALL_DIAL = "call.dial"
    CALL_HANGUP = "call.hangup"
    CALL_HOLD = "call.hold"
    CALL_RESUME = "call.resume"
    CALL_TRANSFER = "call.transfer"
    CALL_CONFERENCE = "call.conference"
    CALL_SEND_DTMF = "call.send_dtmf"
    CALL_MONITORING = "call.monitoring"
    DEVICE_MONITORING = "device.monitoring"
    DIRECTORY_LOOKUP = "directory.lookup"
    MEDIA_TERMINATION = "media.termination"

    # monitor routing
    MONITOR_ROUTE = "monitor.route"
    MONITOR_LAYOUT_PROFILES = "monitor.layout_profiles"

    # video
    VIDEO_RESOLVE_CAMERA = "video.resolve_camera"
    VIDEO_OPEN_CAMERA = "video.open_camera"
    VIDEO_FOCUS_CAMERA = "video.focus_camera"
    VIDEO_OPEN_CAMERA_GROUP = "video.open_camera_group"
    VIDEO_OPEN_ALARM_CONTEXT = "video.open_alarm_context"

    # alarm ingress
    ALARM_SUBSCRIBE = "alarm.subscribe"
    ALARM_RESOLVE_SOURCE = "alarm.resolve_source"
    ALARM_GET_CONTEXT = "alarm.get_context"
    ALARM_ACKNOWLEDGE_EXTERNAL = "alarm.acknowledge_external"

    # weather
    WEATHER_WARNINGS = "weather.warnings"
    WEATHER_RADAR = "weather.radar"
    WEATHER_OBSERVATIONS = "weather.observations"


class CapabilitySet:
    """Immutable set of capabilities with safe membership checks."""

    __slots__ = ("_items",)

    def __init__(self, items: Iterable[Capability | str] = ()) -> None:
        resolved: set[Capability] = set()
        for it in items:
            resolved.add(it if isinstance(it, Capability) else Capability(it))
        self._items = frozenset(resolved)

    def has(self, cap: Capability | str) -> bool:
        try:
            wanted = cap if isinstance(cap, Capability) else Capability(cap)
        except ValueError:
            return False
        return wanted in self._items

    def require(self, cap: Capability | str) -> None:
        if not self.has(cap):
            raise CapabilityNotSupported(str(cap))

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(sorted(self._items, key=str))

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CapabilitySet) and other._items == self._items

    def __repr__(self) -> str:
        return f"CapabilitySet({sorted(map(str, self._items))!r})"


class CapabilityNotSupported(RuntimeError):
    def __init__(self, capability: str) -> None:
        super().__init__(f"Integration does not support capability: {capability}")
        self.capability = capability
