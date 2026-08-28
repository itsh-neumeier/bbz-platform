from __future__ import annotations


class IntegrationError(RuntimeError):
    """Base class for integration-side failures surfaced to the core."""


class NotConfigured(IntegrationError):
    """Integration is enabled but its configuration is missing/invalid."""


class ProviderUnavailable(IntegrationError):
    """Upstream provider (PBX, VMS, ...) is unreachable."""
