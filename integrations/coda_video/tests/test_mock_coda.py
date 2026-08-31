from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.manifest import ManifestError, validate_manifest
from bbz_integration_sdk.providers import (
    ALARM_INGRESS_METHODS,
    VIDEO_METHODS,
    AlarmContext,
    AlarmIngressProvider,
    AlarmSource,
    CameraNotFoundError,
    CameraOpenFailed,
    CameraView,
    ExternalAckCapable,
    IncomingAlarm,
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
    p.simulate_alarm(
        {"id": "e1", "source": "CODA-ALARM-4711", "subtype": "panic_button", "cameras": ["CAM-1"]}
    )
    got = [e async for e in p.subscribe_alarms()]
    assert len(got) == 1
    assert isinstance(got[0], IncomingAlarm)
    assert got[0].provider_event_id == "e1"
    assert got[0].alarm_subtype == "panic_button"
    assert got[0].raw["id"] == "e1"  # the vendor payload survives only here

    src = await p.resolve_source(external_source_id="CODA-ALARM-4711")
    assert isinstance(src, AlarmSource) and src.name == "SP Nbg"
    assert await p.resolve_source(external_source_id="UNKNOWN") is None


async def test_alarm_ingress_interface_is_complete_and_typed() -> None:
    p = MockCodaVideoProvider(simulated_sources=[])
    for method in ALARM_INGRESS_METHODS:
        assert callable(getattr(p, method))
    ctx = await p.get_context(provider_event_id="e1")
    assert isinstance(ctx, AlarmContext) and ctx.provider_event_id == "e1"


def test_external_ack_is_opt_in_and_separate_from_the_bbz_event_ack() -> None:
    # the mock does not declare alarm.acknowledge_external, so it is not ack-capable
    assert not isinstance(MockCodaVideoProvider(), ExternalAckCapable)
    assert "alarm.acknowledge_external" not in _MANIFEST["capabilities"]


# --- E16-09: full simulation (.ai/INTEGRATIONS_CODA_VIDEO.md "Testing") ---

_ALARM_SOURCES = [
    {"external_source_id": "SP-NBG", "name": "SP Nbg", "cameras": ["CAM-1", "CAM-2"]},
]


@pytest.mark.parametrize(
    ("raw", "expected_type", "expected_subtype"),
    [
        (
            {"id": "a1", "source": "SP-NBG", "type": "panic", "subtype": "panic_button"},
            "panic",
            "panic_button",
        ),
        ({"id": "a2", "source": "SP-NBG", "type": "intrusion"}, "intrusion", None),
        ({"id": "a3", "source": "SP-NBG"}, "technical_alarm", None),
    ],
)
async def test_panic_intrusion_and_generic_alarms_all_flow_through(
    raw: dict, expected_type: str, expected_subtype: str | None
) -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.simulate_alarm(raw)
    got = [a async for a in p.subscribe_alarms()]
    assert len(got) == 1
    assert got[0].alarm_type == expected_type
    assert got[0].alarm_subtype == expected_subtype


async def test_get_associated_cameras_returns_the_alarm_cameras() -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.simulate_alarm(
        {"id": "a1", "source": "SP-NBG", "subtype": "panic_button", "cameras": ["CAM-1", "CAM-2"]}
    )
    p.simulate_alarm({"id": "a2", "source": "SP-NBG", "cameras": ["CAM-9"]})
    assert await p.get_associated_cameras(provider_event_id="a1") == ["CAM-1", "CAM-2"]
    assert await p.get_associated_cameras(provider_event_id="a2") == ["CAM-9"]
    assert await p.get_associated_cameras(provider_event_id="unknown") == []
    ctx = await p.get_context(provider_event_id="a1")
    assert ctx.associated_camera_ids == ["CAM-1", "CAM-2"]


async def test_an_unmapped_source_resolves_to_none() -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.simulate_alarm({"id": "a1", "source": "NOT-CONFIGURED"})
    got = [a async for a in p.subscribe_alarms()]
    assert got[0].source_external_id == "NOT-CONFIGURED"
    assert await p.resolve_source(external_source_id="NOT-CONFIGURED") is None


async def test_a_duplicated_alarm_keeps_its_identity() -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.simulate_alarm({"id": "dup", "source": "SP-NBG"})
    p.simulate_alarm({"id": "dup", "source": "SP-NBG"})
    got = [a async for a in p.subscribe_alarms()]
    assert [a.provider_event_id for a in got] == ["dup", "dup"]


async def test_a_reconnect_replays_the_backlog() -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.simulate_alarm({"id": "r1", "source": "SP-NBG", "subtype": "panic_button"})

    first = [a async for a in p.subscribe_alarms()]
    assert [a.provider_event_id for a in first] == ["r1"]
    assert [a async for a in p.subscribe_alarms()] == []  # drained

    p.reconnect()
    replayed = [a async for a in p.subscribe_alarms()]
    assert [a.provider_event_id for a in replayed] == ["r1"]  # same alarm, same id


async def test_a_failing_camera_raises_on_open_and_focus_and_group() -> None:
    p = MockCodaVideoProvider(simulated_sources=_ALARM_SOURCES)
    p.fail_cameras("CAM-2")

    with pytest.raises(CameraOpenFailed):
        await p.open_camera(camera_id="CAM-2", workplace_id="wp", command_id="c1")
    with pytest.raises(CameraOpenFailed):
        await p.focus_camera(camera_id="CAM-2", workplace_id="wp", command_id="c2")
    with pytest.raises(CameraOpenFailed):
        await p.open_camera_group(camera_ids=["CAM-1", "CAM-2"], workplace_id="wp", command_id="c3")

    # a group without the failing camera still succeeds
    ok = await p.open_camera_group(camera_ids=["CAM-1"], workplace_id="wp", command_id="c4")
    assert ok.camera_ids == ["CAM-1"]

    p.clear_camera_failures()
    view = await p.open_camera(camera_id="CAM-2", workplace_id="wp", command_id="c5")
    assert view.action == "opened"


async def test_camera_failures_are_configurable_via_build_and_shown_in_health() -> None:
    p = build({"simulated_sources": _ALARM_SOURCES, "camera_failures": ["CAM-1"]})
    with pytest.raises(CameraOpenFailed):
        await p.open_camera(camera_id="CAM-1", workplace_id="wp", command_id="c1")
    report = await p.health()
    assert report.details["failing_cameras"] == "CAM-1"


async def test_the_manifest_still_validates_with_the_new_config_field() -> None:
    schema = json.loads((Path(__file__).parents[1] / "config_schema.json").read_text("utf-8"))
    assert "camera_failures" in schema["properties"]
    assert schema["additionalProperties"] is False
