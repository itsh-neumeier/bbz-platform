"""Vendor-neutral provider protocols.

Each protocol is the contract the BBZ core codes against. A concrete integration
implements the protocol for its domain; the core never imports the integration.

Foundation phase: signatures only. Payload models (normalized call model, camera
reference, alarm context, ...) are finalized alongside the first real provider in
their respective phases, strictly from official vendor documentation.
"""

from bbz_integration_sdk.providers.alarm_ingress import AlarmIngressProvider
from bbz_integration_sdk.providers.base import Provider, ProviderInfo
from bbz_integration_sdk.providers.monitor import MonitorProvider
from bbz_integration_sdk.providers.telephony import TELEPHONY_METHODS, TelephonyProvider
from bbz_integration_sdk.providers.telephony_types import (
    TELEPHONY_CAPABILITIES,
    CallDirection,
    CallerResolution,
    CallEvent,
    CallLifecycleState,
    CallSnapshot,
    CommandAccepted,
    LineInfo,
    LineState,
    PartyRef,
    ReconcileResult,
)
from bbz_integration_sdk.providers.video import VIDEO_METHODS, VideoProvider
from bbz_integration_sdk.providers.video_types import (
    VIDEO_CAPABILITIES,
    AlarmContextView,
    CameraGroupView,
    CameraNotFoundError,
    CameraView,
    ResolvedCamera,
    VideoProviderError,
    VideoTimeoutError,
)
from bbz_integration_sdk.providers.weather import WeatherProvider

__all__ = [
    "TELEPHONY_CAPABILITIES",
    "TELEPHONY_METHODS",
    "VIDEO_CAPABILITIES",
    "VIDEO_METHODS",
    "AlarmContextView",
    "AlarmIngressProvider",
    "CallDirection",
    "CallEvent",
    "CallLifecycleState",
    "CallSnapshot",
    "CallerResolution",
    "CameraGroupView",
    "CameraNotFoundError",
    "CameraView",
    "CommandAccepted",
    "LineInfo",
    "LineState",
    "MonitorProvider",
    "PartyRef",
    "Provider",
    "ProviderInfo",
    "ReconcileResult",
    "ResolvedCamera",
    "TelephonyProvider",
    "VideoProvider",
    "VideoProviderError",
    "VideoTimeoutError",
    "WeatherProvider",
]
