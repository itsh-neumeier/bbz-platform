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

import asyncio
import contextlib
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
#: background provider-shutdown tasks kept referenced so the GC does not drop them
_PENDING_SHUTDOWNS: set[asyncio.Task[None]] = set()


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
    from bbz_core.infra.repositories.sip_trunk_config import SipTrunkConfigService
    from bbz_core.infra.sip_secrets import SipSecretsNotConfigured

    try:
        async with session_scope() as session:
            config = await SipConfigService(session).runtime_config()
            if config is not None:
                _merge_trunk_outbound(
                    config, await SipTrunkConfigService(session).outbound_line_map()
                )
            return config
    except SipSecretsNotConfigured:
        return None


def _merge_trunk_outbound(config: dict[str, Any], trunk_lines: dict[str, dict[str, str]]) -> None:
    """Fold the trunk-backed outbound line templates (ADR-0034 / E13-10) into the
    ``config_schema.json`` shape so ``dial`` can route through a trunk."""
    if not trunk_lines:
        return
    endpoints = dict(config.get("line_endpoints") or {})
    caller_ids = dict(config.get("line_caller_ids") or {})
    lines = list(config.get("lines") or [])
    for line_id, info in trunk_lines.items():
        endpoints[line_id] = info["endpoint"]
        caller_ids[line_id] = info["caller_id"]
        if line_id not in lines:
            lines.append(line_id)
    config["line_endpoints"] = endpoints
    config["line_caller_ids"] = caller_ids
    config["lines"] = lines


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
    """Drop the cached ``telephony_sip`` provider so the next
    :func:`active_telephony_provider` rebuilds it from the new DB config (the SIP
    admin API calls this after a write, ADR-0033).

    A no-op unless ``telephony_sip`` is the *active* provider — a SIP config
    change must not touch the mock or a CUCM session. The shutdown runs in the
    background so a slow ARI teardown never blocks the admin request."""
    if get_settings().telephony_integration_id != "telephony_sip":
        return
    provider = _CACHE.pop("telephony:telephony_sip", None)
    shutdown = getattr(provider, "shutdown", None) if provider is not None else None
    if callable(shutdown):
        task = asyncio.create_task(_safe_shutdown(shutdown))
        _PENDING_SHUTDOWNS.add(task)
        task.add_done_callback(_PENDING_SHUTDOWNS.discard)


async def _safe_shutdown(shutdown: object) -> None:
    with contextlib.suppress(Exception):
        await shutdown()  # type: ignore[operator]


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


async def probe_sip_trunk(trunk_id: str) -> tuple[str, str]:
    """Ask the configured Asterisk (via ARI ``GET /endpoints``) whether the
    generated ``PJSIP/<trunk_id>`` endpoint is loaded — the admin "test trunk"
    button (ADR-0034). Returns ``(state, detail)`` with ``state`` in
    ``online | loaded | not_loaded | unreachable``. Never raises.

    ARI reports a PJSIP endpoint as ``online`` only when it has a reachable AOR
    contact; an **inbound-only** trunk (identify-by-IP) and a trunk whose
    REGISTER has not yet succeeded both show as ``offline`` there — which does
    not mean misconfigured. So ARI ``offline`` / ``unknown`` is reported as
    ``loaded`` (config is on the box) with a pointer at
    ``pjsip show registrations`` for the real registration state, which ARI
    cannot see."""
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.sip_config import SipConfigService
    from bbz_core.infra.sip_secrets import SipSecretsNotConfigured

    try:
        async with session_scope() as session:
            config = await SipConfigService(session).runtime_config(for_probe=True)
    except SipSecretsNotConfigured:
        config = None
    if config is None:
        return "unreachable", "the SIP gateway (Asterisk/ARI) is not configured"

    lm = _manifest_for("telephony", "telephony_sip")
    provider = cast("TelephonyProvider", _load(lm.manifest.adapter, config))
    try:
        endpoints = await provider.gateway_endpoints()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return "unreachable", "Asterisk ARI is not reachable"
    finally:
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            await shutdown()

    return _trunk_probe_state(endpoints, trunk_id)


def _trunk_probe_state(endpoints: list[Any], trunk_id: str) -> tuple[str, str]:
    """Map an ARI ``GET /endpoints`` list to ``(state, detail)`` for one trunk.
    Pure — the network part is in :func:`probe_sip_trunk`."""
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        if str(ep.get("technology", "")).lower() == "pjsip" and ep.get("resource") == trunk_id:
            ari_state = str(ep.get("state") or "unknown")
            channels = len(ep.get("channel_ids") or [])
            if ari_state == "online":
                return "online", f"PJSIP/{trunk_id} is online ({channels} active channel(s))"
            return "loaded", (
                f"PJSIP/{trunk_id} is loaded (ARI: {ari_state}). A registering trunk "
                "shows 'online' only after a successful REGISTER — check "
                "'pjsip show registrations' on the Asterisk box for the trunk / "
                "per-number registration state."
            )
    return (
        "not_loaded",
        f"PJSIP/{trunk_id} is not loaded — run the sync script and 'pjsip reload'",
    )


def loaded_providers() -> dict[str, Provider]:
    """The providers already initialised in this process, keyed
    ``"<domain>:<integration_id>"``. Read-only view for the metrics scrape
    (E22-02) — it never triggers a load."""
    return dict(_CACHE)


def reset_provider_cache() -> None:
    """Drop every cached provider — call between tests."""
    _CACHE.clear()
