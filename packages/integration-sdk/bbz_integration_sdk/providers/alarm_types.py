"""Vendor-neutral payload models for the alarm-ingress provider protocol (E16-03).

A ``coda_video`` (or future) alarm adapter translates its vendor alarm objects
*into* these shapes. Nothing here is a Coda / Qognify / HxGN detail; the vendor
payload survives only as the opaque :attr:`IncomingAlarm.raw` dict, kept for the
E16-04 hash / diagnostics reference and **never** read by core business rules.

**BBZ event acknowledgement and external alarm acknowledgement are separate
domain actions** (``.ai/INTEGRATIONS_CODA_VIDEO.md``). ``acknowledge_external``
only tells the *vendor* system an operator saw the alarm; it never accepts,
acknowledges or closes the BBZ event. It exists only when the manifest declares
``alarm.acknowledge_external`` — a real adapter adds it solely if the official
Coda / HxGN dC3 interface supports it.
"""

from __future__ import annotations

import datetime as _dt

from pydantic import BaseModel, ConfigDict, Field

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.errors import IntegrationError

ALARM_INGRESS_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.ALARM_SUBSCRIBE,
        Capability.ALARM_RESOLVE_SOURCE,
        Capability.ALARM_GET_CONTEXT,
        Capability.ALARM_GET_ASSOCIATED_CAMERAS,
    }
)
#: only present when the manifest declares it
ALARM_ACK_EXTERNAL_CAPABILITY: Capability = Capability.ALARM_ACKNOWLEDGE_EXTERNAL


class AlarmProviderError(IntegrationError):
    pass


class AlarmSourceNotFoundError(AlarmProviderError):
    """No alarm source resolves for the given external source id."""


class ExternalAckNotSupportedError(AlarmProviderError):
    """acknowledge_external was called but the provider / vendor does not offer it."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IncomingAlarm(_Model):
    """One alarm as the provider hands it over — *before* E16-04 normalisation.

    Carries the identifiers and the raw payload the normaliser needs; the raw
    payload is diagnostics-only. Either ``provider_event_id`` is a stable vendor
    id, or it is ``None`` and E16-04 derives a deterministic dedupe key.
    """

    provider: str = Field(min_length=1)
    provider_instance_id: str
    provider_event_id: str | None = None
    provider_alarm_id: str | None = None
    alarm_type: str
    alarm_subtype: str | None = None
    source_external_id: str
    source_name: str | None = None
    site_external_id: str | None = None
    occurred_at: _dt.datetime | None = None
    received_at: _dt.datetime
    severity_external: str | None = None
    state_external: str | None = None
    associated_camera_ids: list[str] = Field(default_factory=list)
    #: the vendor payload — referenced / hashed by E16-04, never parsed by rules
    raw: dict[str, object] = Field(default_factory=dict)


class AlarmSource(_Model):
    external_source_id: str
    name: str | None = None
    site_external_id: str | None = None
    associated_camera_ids: list[str] = Field(default_factory=list)


class AlarmContext(_Model):
    provider_event_id: str
    source: AlarmSource | None = None
    associated_camera_ids: list[str] = Field(default_factory=list)


class ExternalAckResult(_Model):
    """Result of telling the **vendor** system an operator saw the alarm.
    Unrelated to the BBZ event lifecycle."""

    provider_event_id: str
    command_id: str
    acknowledged_external: bool
