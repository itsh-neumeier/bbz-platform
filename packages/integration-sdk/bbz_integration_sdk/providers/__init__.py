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
from bbz_integration_sdk.providers.telephony import TelephonyProvider
from bbz_integration_sdk.providers.video import VideoProvider
from bbz_integration_sdk.providers.weather import WeatherProvider

__all__ = [
    "AlarmIngressProvider",
    "MonitorProvider",
    "Provider",
    "ProviderInfo",
    "TelephonyProvider",
    "VideoProvider",
    "WeatherProvider",
]
