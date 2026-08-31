"""Vendor-neutral payload models for the video provider protocol (E16-02).

These are the BBZ platform's own contract. A ``coda_video`` (HxGN dC3 Video)
adapter translates its vendor camera / display objects *into* these shapes;
nothing here is a Coda / Qognify / HxGN detail, and no vendor object id ever
crosses this boundary — the core addresses cameras only by the normalized
``camera_id`` that :meth:`VideoProvider.resolve_camera` returns.

Every control method takes a ``command_id`` (the caller's idempotency key) and a
``workplace_id`` (the bound BBZ workplace the view is for). Errors are the typed
:class:`VideoProviderError` hierarchy; a provider that cannot answer within its
own deadline raises :class:`VideoTimeoutError` rather than blocking.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.errors import IntegrationError

VIDEO_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.VIDEO_RESOLVE_CAMERA,
        Capability.VIDEO_OPEN_CAMERA,
        Capability.VIDEO_FOCUS_CAMERA,
        Capability.VIDEO_OPEN_CAMERA_GROUP,
        Capability.VIDEO_OPEN_ALARM_CONTEXT,
    }
)


class VideoProviderError(IntegrationError):
    """A video operation failed. Subclasses carry the specific reason."""


class CameraNotFoundError(VideoProviderError):
    """No camera resolves for the given external id / camera id."""


class VideoTimeoutError(VideoProviderError):
    """The provider did not complete the operation within its deadline."""


class CameraOpenFailed(VideoProviderError):
    """A camera resolves but the open / focus operation failed at the provider."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ResolvedCamera(_Model):
    """A camera the core can address. ``camera_id`` is the normalized handle used
    by every other method — never the vendor's own object id."""

    camera_id: str = Field(min_length=1)
    name: str
    site: str | None = None
    online: bool = True
    group_ids: list[str] = Field(default_factory=list)


class CameraView(_Model):
    """Result of opening or focusing one camera on a workplace."""

    camera_id: str
    workplace_id: str
    command_id: str
    #: "opened" | "focused"
    action: str
    preset: str | None = None


class CameraGroupView(_Model):
    camera_ids: list[str]
    workplace_id: str
    command_id: str


class AlarmContextView(_Model):
    """The camera set the provider associates with an alarm, opened together."""

    alarm_ref: str
    workplace_id: str
    command_id: str
    camera_ids: list[str] = Field(default_factory=list)
