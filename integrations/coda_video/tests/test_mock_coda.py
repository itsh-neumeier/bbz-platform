from __future__ import annotations

from bbz_integration_sdk.providers import AlarmIngressProvider, VideoProvider
from integrations.coda_video.adapter import MockCodaVideoProvider, normalize_alarm


def test_satisfies_both_protocols() -> None:
    p = MockCodaVideoProvider()
    assert isinstance(p, VideoProvider)
    assert isinstance(p, AlarmIngressProvider)


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
