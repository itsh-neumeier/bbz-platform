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
from bbz_integration_sdk.providers import Provider, TelephonyProvider

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


async def active_telephony_provider() -> TelephonyProvider:
    integration_id = get_settings().telephony_integration_id
    key = f"telephony:{integration_id}"
    if key not in _CACHE:
        lm = _manifest_for("telephony", integration_id)
        provider = _load(lm.manifest.adapter, None)
        await provider.initialize()
        _CACHE[key] = provider
    return cast("TelephonyProvider", _CACHE[key])


def reset_provider_cache() -> None:
    """Drop every cached provider — call between tests."""
    _CACHE.clear()
