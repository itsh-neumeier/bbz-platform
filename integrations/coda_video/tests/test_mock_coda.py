from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.manifest import ManifestError, validate_manifest
from bbz_integration_sdk.providers import (
    VIDEO_METHODS,
    AlarmIngressProvider,
    CameraNotFoundError,
    CameraView,
    ResolvedCamera,
    VideoProvider,
)
from integrations.coda_video.adapter import MockCodaVideoProvider, build, normalize_alarm

_MANIFEST = json.loads((Path(__file__).parents[1] / "manifest.json").read_text("utf-8"))

_SOURCES = [
    {"external_source_id": "SP-NBG", "name": "SP Nbg", "cameras": ["CAM-1", "CAM-2"]},
]


def test_satisfies_both_protocols() -> None:
    p = MockCodaVideoProvider()
    assert isinstance(p, VideoProvider)
    assert isinstance(p, AlarmIngressProvider)
    for method in VIDEO_METHODS:
        assert callable(getattr(p, method))


def test_manifest_is_valid_with_two_independent_capability_groups() -> None:
    m = validate_manifest(_MANIFEST)
    assert m.id == "coda_video"  # canonical id everywhere (ADR-0016)
    assert m.legacy_display_alias == "Cayuga"  # display only
    assert set(m.capability_groups) == {"video", "alarm_ingress"}
    # every grouped capability is also declared top-level
    for caps in m.capability_groups.values():
        assert set(caps) <= set(m.capabilities)


def test_a_group_capability_not_in_capabilities_is_rejected() -> None:
    bad = {**_MANIFEST, "capability_groups": {"video": ["video.teleport"]}}
    with pytest.raises(ManifestError):
        validate_manifest(bad)


def test_each_capability_group_activates_independently() -> None:
    video_only = build({"enabled_capability_groups": ["video"]})
    assert video_only.enabled_capability_groups() == ("video",)
    assert video_only.capabilities().has("video.open_camera")
    assert not video_only.capabilities().has("alarm.subscribe")

    alarm_only = build({"enabled_capability_groups": ["alarm_ingress"]})
    assert alarm_only.capabilities().has("alarm.subscribe")
    assert not alarm_only.capabilities().has("video.open_camera")

    assert build().enabled_capability_groups() == ("video", "alarm_ingress")


def test_an_unknown_capability_group_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown capability group"):
        MockCodaVideoProvider(enabled_capability_groups=["nope"])


async def test_video_interface_returns_typed_normalized_results() -> None:
    p = MockCodaVideoProvider(simulated_sources=_SOURCES)

    cam = await p.resolve_camera(external_id="CAM-1")
    assert isinstance(cam, ResolvedCamera)
    assert cam.camera_id == "CAM-1" and cam.group_ids == ["SP-NBG"]

    opened = await p.open_camera(camera_id="CAM-1", workplace_id="wp-1", command_id="c1")
    assert isinstance(opened, CameraView) and opened.action == "opened"

    focused = await p.focus_camera(
        camera_id="CAM-1", workplace_id="wp-1", command_id="c2", preset="entrance"
    )
    assert focused.action == "focused" and focused.preset == "entrance"

    grp = await p.open_camera_group(
        camera_ids=["CAM-1", "CAM-2"], workplace_id="wp-1", command_id="c3"
    )
    assert grp.camera_ids == ["CAM-1", "CAM-2"]

    ctx = await p.open_alarm_context(alarm_ref="A-1", workplace_id="wp-1", command_id="c4")
    assert ctx.camera_ids == ["CAM-1", "CAM-2"]


async def test_resolve_camera_raises_camera_not_found_for_an_unknown_id() -> None:
    p = MockCodaVideoProvider(simulated_sources=_SOURCES)
    with pytest.raises(CameraNotFoundError):
        await p.resolve_camera(external_id="CAM-NOPE")


def test_no_vendor_object_id_fields_in_the_result_models() -> None:
    # the interface never carries a Coda/Qognify object id — only our normalized handles
    for field in ResolvedCamera.model_fields:
        assert "vendor" not in field and "qognify" not in field and "coda_object" not in field


def test_normalize_alarm_has_stable_identity() -> None:
    raw = {
        "id": "CODA-EVT-4711",
        "type": "panic",
        "subtype": "panic_button",
        "source": "CODA-ALARM-4711",
        "source_name": "Ueberfalltaster ServicePoint Nuernberg Hbf",
        "cameras": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
    }
    a = normalize_alarm(raw, instance_id="coda-mock-1")
    b = normalize_alarm(raw, instance_id="coda-mock-1")
    assert a["provider_event_id"] == b["provider_event_id"] == "CODA-EVT-4711"
    assert a["provider"] == "coda_video"
    assert a["associated_cameras"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]


async def test_simulate_and_consume_alarm() -> None:
    p = MockCodaVideoProvider(
        simulated_sources=[
            {"external_source_id": "CODA-ALARM-4711", "name": "SP Nbg", "cameras": ["CAM-1"]}
        ]
    )
    p.simulate_alarm({"id": "e1", "source": "CODA-ALARM-4711", "subtype": "panic_button"})
    got = [e async for e in p.subscribe_alarms()]
    assert len(got) == 1
    assert got[0]["provider_event_id"] == "e1"

    src = await p.resolve_source(external_source_id="CODA-ALARM-4711")
    assert src is not None and src["name"] == "SP Nbg"
