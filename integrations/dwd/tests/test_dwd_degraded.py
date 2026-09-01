"""DWD adapter degraded paths (roadmap E18-10): every way a real DWD response
can be broken or thin, exercised through the real ``DwdWeatherProvider`` with a
stubbed transport — a corrupt zip, a truncated CAP member, a POI CSV with only
``---``, a GetCapabilities without a usable ``time`` dimension. The adapter
either raises its typed error (E18-06 then keeps the last-good snapshot and marks
health ``degraded``) or returns a thin-but-valid list — never a bare crash.

No network: the transport is always a stub. See ``test_dwd_no_network.py`` for
the socket-level guarantee.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from integrations.dwd.adapter import build
from integrations.dwd.observations import DwdObservationsClient, DwdObservationsError, parse_poi_csv
from integrations.dwd.radar import DwdRadarClient, DwdRadarError
from integrations.dwd.warnings import DwdWarningsClient, DwdWarningsError

_FX = Path(__file__).resolve().parent / "fixtures"
_ZIP_LISTING = b'<a href="Z_CAP_C_EDZW_20260901120000_PVW_STATUS_PREMIUMDWD_DISTRICT_DE.zip">x</a>'


# --- warnings ----------------------------------------------------------------


class _WarnStub(DwdWarningsClient):
    def __init__(self, *, listing: bytes = _ZIP_LISTING, zip_bytes: bytes = b"") -> None:
        super().__init__("https://example.invalid/DISTRICT_DWD_STAT/")
        self._listing = listing
        self._zip = zip_bytes

    def _get(self, url: str) -> bytes:
        return self._listing if url.endswith("/") else self._zip


def _zip_of(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


async def test_a_corrupt_zip_raises_dwd_warnings_error() -> None:
    provider = build({})
    provider._warnings_client = _WarnStub(zip_bytes=b"PK\x03\x04 not really a zip")  # type: ignore[attr-defined]
    with pytest.raises(DwdWarningsError):
        await provider.get_warnings(region="mittelfranken")


async def test_a_feed_listing_without_a_district_zip_raises() -> None:
    provider = build({})
    provider._warnings_client = _WarnStub(listing=b"<html>nothing here</html>")  # type: ignore[attr-defined]
    with pytest.raises(DwdWarningsError):
        await provider.get_warnings(region="mittelfranken")


async def test_a_truncated_cap_member_fails_the_whole_fetch() -> None:
    good = (_FX / "cap_district" / "mittelfranken_multi_area.xml").read_bytes()
    truncated = good[: len(good) // 2]
    provider = build({})
    provider._warnings_client = _WarnStub(  # type: ignore[attr-defined]
        zip_bytes=_zip_of({"a.xml": good, "b.xml": truncated})
    )
    with pytest.raises(DwdWarningsError):
        await provider.get_warnings(region="mittelfranken")


async def test_a_cap_alert_with_only_a_non_german_info_yields_nothing() -> None:
    xml = (
        b'<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">'
        b"<identifier>2.49.0.0.276.0.DWD.PVW.en-only.DEU</identifier>"
        b"<status>Actual</status><msgType>Alert</msgType>"
        b"<info><language>en-GB</language><event>SQUALLS</event><severity>Moderate</severity>"
        b"<area><areaDesc>City of Nuremberg</areaDesc>"
        b"<geocode><valueName>WARNCELLID</valueName><value>109564000</value></geocode>"
        b"</area></info></alert>"
    )
    provider = build({})
    provider._warnings_client = _WarnStub(zip_bytes=_zip_of({"a.xml": xml}))  # type: ignore[attr-defined]
    assert await provider.get_warnings(region="mittelfranken") == []


# --- observations ----------------------------------------------------------


class _ObsStub(DwdObservationsClient):
    def __init__(self, payload: bytes) -> None:
        super().__init__("https://example.invalid/poi/")
        self._payload = payload

    def _get(self, station_id: str) -> bytes:
        return self._payload


def test_a_poi_csv_that_is_all_missing_still_normalizes_to_none_values() -> None:
    csv = (
        "surface observations;Parameter description;"
        "dry_bulb_temperature_at_2_meter_above_ground;relative_humidity\n"
        "10763;Unit;Grad C;%\n"
        "Datum;Uhrzeit (UTC);Temperatur (2m);Relative Feuchte\n"
        "01.09.26;03:00;---;---\n"
    ).encode("latin-1")
    obs = {o.metric: o for o in parse_poi_csv(csv, place="Nürnberg", station_ref="10763")}
    assert obs["temperature"].value is None and obs["humidity"].value is None
    assert obs["temperature"].observed_at.hour == 3


def test_a_poi_csv_with_an_unparseable_timestamp_raises() -> None:
    csv = (
        "surface observations;Parameter description;relative_humidity\n"
        "10763;Unit;%\n"
        "Datum;Uhrzeit (UTC);Relative Feuchte\n"
        "gestern;irgendwann;61\n"
    ).encode("latin-1")
    with pytest.raises(DwdObservationsError):
        parse_poi_csv(csv, place="x", station_ref="10763")


async def test_a_thin_csv_from_the_only_station_raises_all_fail() -> None:
    headers_only = b"surface observations;x\n10763;Unit\nDatum;Uhrzeit (UTC)\n"
    provider = build({"places": [{"name": "Nürnberg", "poi_station_id": "10763"}]})
    provider._observations_client = _ObsStub(headers_only)  # type: ignore[attr-defined]
    with pytest.raises(DwdObservationsError):
        await provider.get_observations(station_ids=[])


# --- radar ---------------------------------------------------------------


class _RadarStub(DwdRadarClient):
    def __init__(self, caps: bytes) -> None:
        super().__init__("https://example.invalid/wms")
        self._caps = caps

    def _get_capabilities(self) -> bytes:
        return self._caps


async def test_capabilities_without_a_time_dimension_raises() -> None:
    caps = (_FX / "wms" / "getcapabilities_no_time.xml").read_bytes()
    provider = build({})
    provider._radar_client = _RadarStub(caps)  # type: ignore[attr-defined]
    with pytest.raises(DwdRadarError):
        await provider.get_radar_frames(area="mittelfranken")


async def test_capabilities_for_a_layer_we_do_not_use_raises() -> None:
    caps = (_FX / "wms" / "getcapabilities_radar.xml").read_bytes()
    provider = build({"radar": {"layer": "Radar_this_layer_is_gone"}})
    provider._radar_client = _RadarStub(caps)  # type: ignore[attr-defined]
    with pytest.raises(DwdRadarError):
        await provider.get_radar_frames(area="mittelfranken")
