from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.manifest import ManifestError, validate_manifest
from bbz_integration_sdk.providers import AlarmIngressProvider, VideoProvider
from integrations.coda_video.adapter import MockCodaVideoProvider, build, normalize_alarm

_MANIFEST = json.loads((Path(__file__).parents[1] / "manifest.json").read_text("utf-8"))


def test_satisfies_both_protocols() -> None:
    p = MockCodaVideoProvider()
    assert isinstance(p, VideoProvider)
    assert isinstance(p, AlarmIngressProvider)


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
