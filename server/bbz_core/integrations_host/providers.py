"""Load and hold integration adapter instances (roadmap E11-06).

An adapter is imported **dynamically** from the string path in its manifest, so
``bbz_core`` never statically imports ``integrations`` (import-linter contract
"Core never imports concrete integrations"). The active provider for a domain is
cached for the process lifetime — a stateful provider (the mock, a real CTI
session) must be a singleton.

Only ``bbz_core.integrations_host`` and ``bbz_core.api`` may reach the SDK; the
domain layer never does.
"""

from __future__ import annotations

import importlib
from typing import Any, cast

from bbz_core.integrations_host.registry import IntegrationRegistry, LoadedManifest
from bbz_core.settings import get_settings
from bbz_integration_sdk.providers import (
    MonitorProvider,
    Provider,
    TelephonyProvider,
    VideoProvider,
    WeatherProvider,
)

_CACHE: dict[str, Provider] = {}


class NoActiveProvider(RuntimeError):
    """No integration is configured / discoverable for the requested domain."""


def _load(adapter_ref: str, config: dict[str, Any] | None) -> Provider:
    module_path, _, attr = adapter_ref.partition(":")
    module = importlib.import_module(module_path)
    builder = getattr(module, "build", None)
    if callable(builder):
        return cast("Provider", builder(config or {}))
    return cast("Provider", getattr(module, attr)())


def _manifest_for(domain: str, integration_id: str) -> LoadedManifest:
    for lm in IntegrationRegistry.discover():
        if lm.manifest.domain == domain and lm.manifest.id == integration_id:
            return lm
    raise NoActiveProvider(f"no {domain!r} integration named {integration_id!r}")


async def _telephony_sip_config(integration_id: str) -> dict[str, Any] | None:
    """The DB-backed gateway config for ``telephony_sip`` (ADR-0033). ``None``
    for any other adapter, or when the gateway is unconfigured / disabled / its
    encryption key is missing (the provider then stays an inert scaffold)."""
    if integration_id != "telephony_sip":
        return None
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.sip_config import SipConfigService
    from bbz_core.infra.sip_secrets import SipSecretsNotConfigured

    try:
        async with session_scope() as session:
            return await SipConfigService(session).runtime_config()
    except SipSecretsNotConfigured:
        return None


async def active_telephony_provider() -> TelephonyProvider:
    integration_id = get_settings().telephony_integration_id
    key = f"telephony:{integration_id}"
    if key not in _CACHE:
        lm = _manifest_for("telephony", integration_id)
        provider = _load(lm.manifest.adapter, await _telephony_sip_config(integration_id))
        await provider.initialize()
        _CACHE[key] = provider
    return cast("TelephonyProvider", _CACHE[key])


async def evict_telephony_provider() -> None:
    """Drop (and shut down) the cached telephony provider so the next
    :func:`active_telephony_provider` rebuilds it — e.g. after the SIP gateway
    config changed in the admin API (ADR-0033)."""
    integration_id = get_settings().telephony_integration_id
    provider = _CACHE.pop(f"telephony:{integration_id}", None)
    if provider is not None:
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            await shutdown()


async def active_video_provider() -> VideoProvider:
    integration_id = get_settings().video_integration_id
    key = f"video:{integration_id}"
    if key not in _CACHE:
        lm = _manifest_for("video", integration_id)
        provider = _load(lm.manifest.adapter, None)
        await provider.initialize()
        _CACHE[key] = provider
    return cast("VideoProvider", _CACHE[key])


async def active_weather_provider() -> WeatherProvider:
    integration_id = get_settings().weather_integration_id
    key = f"weather:{integration_id}"
    if key not in _CACHE:
        lm = _manifest_for("weather", integration_id)
        provider = _load(lm.manifest.adapter, None)
        await provider.initialize()
        _CACHE[key] = provider
    return cast("WeatherProvider", _CACHE[key])


async def active_monitor_provider() -> MonitorProvider:
    integration_id = get_settings().monitor_integration_id
    key = f"monitor:{integration_id}"
    if key not in _CACHE:
        lm = _manifest_for("monitor", integration_id)
        provider = _load(lm.manifest.adapter, None)
        await provider.initialize()
        _CACHE[key] = provider
    return cast("MonitorProvider", _CACHE[key])


async def probe_telephony_sip(config: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Build a throwaway ``telephony_sip`` provider from ``config`` and probe the
    gateway's REST endpoint (no event stream). Returns
    ``(reachable, detail, asterisk_version)`` — the admin "test connection"
    button (ADR-0033). Never raises."""
    lm = _manifest_for("telephony", "telephony_sip")
    provider = cast("TelephonyProvider", _load(lm.manifest.adapter, config))
    try:
        report = await provider.health()
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{type(exc).__name__}", None
    finally:
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            await shutdown()
    version = None
    if isinstance(report.details, dict):
        version = report.details.get("asterisk_version")
    reachable = report.state.value != "unavailable"
    return reachable, report.summary, version if isinstance(version, str) else None


def loaded_providers() -> dict[str, Provider]:
    """The providers already initialised in this process, keyed
    ``"<domain>:<integration_id>"``. Read-only view for the metrics scrape
    (E22-02) — it never triggers a load."""
    return dict(_CACHE)


def reset_provider_cache() -> None:
    """Drop every cached provider — call between tests."""
    _CACHE.clear()
