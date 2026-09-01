"""The DWD parse / normalise path is network-free (roadmap E18-10, AC: "keine
Netzabhängigkeit im PR-CI").

An autouse fixture makes the one primitive every DWD client uses for real I/O —
``urllib.request.urlopen`` — raise, then each adapter is driven end to end over a
stubbed transport against a recorded fixture. If any code path tried a real fetch
(a stray ``urllib`` call, an import-time download) these tests fail loudly
instead of silently reaching out to ``opendata.dwd.de`` / ``maps.dwd.de``.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from integrations.dwd.adapter import build
from integrations.dwd.observations import DwdObservationsClient
from integrations.dwd.radar import DwdRadarClient
from integrations.dwd.warnings import DwdWarningsClient

_FX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def _blocked(*_a: object, **_k: object) -> object:
        raise AssertionError("network access (urllib.request.urlopen) attempted in a DWD unit test")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    yield


class _WarnStub(DwdWarningsClient):
    def __init__(self, zip_bytes: bytes) -> None:
        super().__init__("https://example.invalid/DISTRICT_DWD_STAT/")
        self._zip = zip_bytes

    def _get(self, url: str) -> bytes:
        if url.endswith("/"):
            return (
                b'<a href="Z_CAP_C_EDZW_20260901120000_PVW_STATUS_PREMIUMDWD_DISTRICT_DE.zip">x</a>'
            )
        return self._zip


class _ObsStub(DwdObservationsClient):
    def __init__(self, payload: bytes) -> None:
        super().__init__("https://example.invalid/poi/")
        self._payload = payload

    def _get(self, station_id: str) -> bytes:
        return self._payload


class _RadarStub(DwdRadarClient):
    def __init__(self, caps: bytes) -> None:
        super().__init__("https://example.invalid/wms")
        self._caps = caps

    def _get_capabilities(self) -> bytes:
        return self._caps


async def test_warnings_parse_end_to_end_without_a_socket() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.xml", (_FX / "cap_district" / "mittelfranken_multi_area.xml").read_bytes())
    provider = build({"places": [{"name": "Nürnberg"}]})
    provider._warnings_client = _WarnStub(buf.getvalue())  # type: ignore[attr-defined]
    items = await provider.get_warnings(region="mittelfranken")
    assert items and items[0]["region"] == "Stadt Nürnberg"


async def test_observations_parse_end_to_end_without_a_socket() -> None:
    provider = build({"places": [{"name": "Nürnberg", "poi_station_id": "10763"}]})
    provider._observations_client = _ObsStub((_FX / "poi" / "10763-BEOB.csv").read_bytes())  # type: ignore[attr-defined]
    items = await provider.get_observations(station_ids=[])
    assert {it["metric"] for it in items} >= {"temperature", "humidity"}


async def test_radar_frames_build_end_to_end_without_a_socket() -> None:
    provider = build({"radar": {"frame_count": 4}})
    provider._radar_client = _RadarStub((_FX / "wms" / "getcapabilities_radar.xml").read_bytes())  # type: ignore[attr-defined]
    items = await provider.get_radar_frames(area="mittelfranken")
    assert len(items) == 4
    assert all("maps.dwd.de" not in it["image_ref"] or "GetMap" in it["image_ref"] for it in items)


def test_the_guard_actually_bites() -> None:
    with pytest.raises(AssertionError, match="network access"):
        DwdWarningsClient("https://opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/")._get(
            "https://opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/"
        )
