"""DWD radar frame series (roadmap E18-03): the WMS ``time`` dimension of
``Radar_rv_product_1x1km_ger`` is parsed and turned into a series of GetMap URLs
clipped to the Mittelfranken bbox — the client fetches the images from DWD
directly, we never proxy them.

``fixtures/wms/getcapabilities_radar.xml`` mirrors the real DWD GetCapabilities
(trimmed to the two radar layers).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from integrations.dwd.adapter import build
from integrations.dwd.radar import (
    DwdRadarClient,
    DwdRadarError,
    build_frames,
    parse_time_dimension,
)

_CAPS = (
    Path(__file__).resolve().parent / "fixtures" / "wms" / "getcapabilities_radar.xml"
).read_bytes()


def test_the_time_dimension_gives_the_latest_frame_and_the_step() -> None:
    latest, step = parse_time_dimension(_CAPS, layer="Radar_rv_product_1x1km_ger")
    assert latest == _dt.datetime(2026, 9, 1, 6, 35, tzinfo=_dt.UTC)
    assert step == _dt.timedelta(minutes=5)


def test_a_ten_minute_layer_is_parsed_too() -> None:
    _, step = parse_time_dimension(_CAPS, layer="RADOLAN-RW")
    assert step == _dt.timedelta(minutes=10)


def test_an_unknown_layer_raises() -> None:
    with pytest.raises(DwdRadarError):
        parse_time_dimension(_CAPS, layer="Radar_does_not_exist")


def test_malformed_capabilities_raises() -> None:
    with pytest.raises(DwdRadarError):
        parse_time_dimension(b"<WMS_Capabilities>oops", layer="x")


def test_build_frames_is_a_5_minute_series_oldest_to_newest() -> None:
    latest = _dt.datetime(2026, 9, 1, 6, 35, tzinfo=_dt.UTC)
    frames = build_frames(
        latest,
        _dt.timedelta(minutes=5),
        count=4,
        wms_url="https://maps.dwd.de/geoserver/dwd/wms",
        layer="Radar_rv_product_1x1km_ger",
        bbox=(10.0, 48.9, 11.7, 49.8),
        size=(512, 512),
    )
    assert [f.frame_time.minute for f in frames] == [20, 25, 30, 35]  # oldest → newest
    q = parse_qs(urlparse(frames[-1].image_ref).query)
    assert q["layers"] == ["Radar_rv_product_1x1km_ger"]
    assert q["bbox"] == ["10.0,48.9,11.7,49.8"] and q["crs"] == ["CRS:84"]
    assert q["time"] == ["2026-09-01T06:35:00.000Z"]
    assert q["format"] == ["image/png"]


class _StubRadar(DwdRadarClient):
    def __init__(self, caps: bytes = _CAPS, *, fail: bool = False) -> None:
        super().__init__("https://example.invalid/wms")
        self._caps = caps
        self._fail = fail

    def _get_capabilities(self) -> bytes:
        if self._fail:
            raise DwdRadarError("wms down")
        return self._caps


def test_client_frames_uses_the_capabilities_time_dimension() -> None:
    frames = _StubRadar().frames(count=6)
    assert len(frames) == 6
    assert frames[-1].frame_time == _dt.datetime(2026, 9, 1, 6, 35, tzinfo=_dt.UTC)


async def test_get_radar_frames_returns_frame_item_dicts() -> None:
    provider = build({"radar": {"frame_count": 3, "bbox": [10.5, 49.0, 11.5, 49.6]}})
    provider._radar_client = _StubRadar()  # type: ignore[attr-defined]

    items = await provider.get_radar_frames(area="mittelfranken")
    assert len(items) == 3
    assert all(set(it) == {"frame_time", "image_ref"} for it in items)
    assert "bbox=10.5%2C49.0%2C11.5%2C49.6" in items[0]["image_ref"]  # config bbox


async def test_a_wms_outage_propagates() -> None:
    provider = build({})
    provider._radar_client = _StubRadar(fail=True)  # type: ignore[attr-defined]
    with pytest.raises(DwdRadarError):
        await provider.get_radar_frames(area="mittelfranken")
