"""Operator camera-view helper (roadmap E16-12 / #357, ADR-0032).

The ``bbz_core.api`` layer must not import the integration SDK (import-linter
contract). This module — inside ``integrations_host``, the one part of the core
allowed to touch the SDK — resolves a set of normalized camera refs to a plain,
transport-ready status list and **never raises**: a missing integration or a
per-camera provider error becomes ``online: None`` so the panel degrades to
"Video derzeit nicht verfügbar" instead of failing the request.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from bbz_core.integrations_host.providers import NoActiveProvider, active_video_provider
from bbz_integration_sdk.providers import VideoProviderError


@dataclass(frozen=True)
class CameraStatus:
    ref: str
    name: str
    site: str | None
    online: bool | None
    group_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CameraResolution:
    #: false when there is no active ``video.*`` integration
    provider_available: bool
    cameras: list[CameraStatus]


async def resolve_cameras(refs: Iterable[str]) -> CameraResolution:
    ordered = list(dict.fromkeys(refs))  # dedupe, keep order
    try:
        provider = await active_video_provider()
    except NoActiveProvider:
        return CameraResolution(
            provider_available=False,
            cameras=[CameraStatus(ref=r, name=r, site=None, online=None) for r in ordered],
        )

    out: list[CameraStatus] = []
    for ref in ordered:
        try:
            rc = await provider.resolve_camera(external_id=ref)
            out.append(
                CameraStatus(
                    ref=ref,
                    name=rc.name,
                    site=rc.site,
                    online=rc.online,
                    group_ids=list(rc.group_ids),
                )
            )
        except VideoProviderError:
            out.append(CameraStatus(ref=ref, name=ref, site=None, online=None))
    return CameraResolution(provider_available=True, cameras=out)
