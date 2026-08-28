"""BBZ Integration SDK (vendor-neutral).

Concrete integrations (``integrations/<name>/``) depend on this package to:

* declare a ``manifest.json`` validated against :data:`schemas/manifest.schema.json`
* implement one or more provider ``Protocol`` classes (telephony, monitor, video,
  weather, alarm ingress)
* report health through the diagnostics interface

The BBZ core imports this SDK **only** from ``bbz_core.integrations_host``. The
SDK never imports the core, and it never contains vendor API details — those live
inside each integration and are implemented strictly from official vendor
documentation (RULES.md: "Never invent external API contracts").
"""

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.manifest import IntegrationManifest, ManifestError, validate_manifest

__all__ = [
    "Capability",
    "CapabilitySet",
    "DiagnosticsReport",
    "HealthState",
    "IntegrationManifest",
    "ManifestError",
    "validate_manifest",
]

__version__ = "0.0.0"
