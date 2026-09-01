"""DWD warnings adapter (roadmap E18-02): the CAP 1.2 DISTRICT feed is parsed,
filtered to the configured warncells, and normalised to the E18-06 item contract.
Cancels and geocode-less areas are dropped; a fetch failure raises.

Fixtures under ``fixtures/cap_district/`` are **real** DWD CAP alerts (polygons
stripped) plus two synthetic ones for the Mittelfranken filter + the cancel path.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from integrations.dwd.adapter import build
from integrations.dwd.warnings import (
    DwdWarningsClient,
    DwdWarningsError,
    parse_cap_alerts,
)

_FX = Path(__file__).resolve().parent / "fixtures" / "cap_district"


def _fx(name: str) -> bytes:
    return (_FX / name).read_bytes()


# --- pure parser ---------------------------------------------------------


def test_a_real_alert_parses_to_the_normalized_contract() -> None:
    alerts = parse_cap_alerts(_fx("real_sturmboeen_alert.xml"))
    assert len(alerts) == 1
    a = alerts[0]
    assert a.type == "STURMBÖEN" and a.level == "2"  # severity Moderate
    assert a.region == "Kreis Harz - Bergland (Oberharz)"
    assert a.warncell_id == "915085002"
    assert a.headline == "Amtliche WARNUNG vor STURMBÖEN"
    assert a.valid_from is not None and a.valid_from.tzinfo is not None
    assert a.valid_to is not None and a.valid_to > a.valid_from
    assert "Handlungsempfehlungen" in (a.description or "")  # instruction appended
    assert a.source_ref.startswith("2.49.0.0.276.0.DWD.PVW.")


def test_a_cancel_message_yields_nothing() -> None:
    assert parse_cap_alerts(_fx("cancelled.xml")) == []


def test_one_alert_over_several_areas_is_one_row_per_area() -> None:
    alerts = parse_cap_alerts(_fx("mittelfranken_multi_area.xml"))
    assert {a.region for a in alerts} == {"Stadt Nürnberg", "Stadt Fürth", "Kreis Passau"}
    assert {a.warncell_id for a in alerts} == {"109564000", "109563000", "109275000"}
    assert all(a.source_ref.endswith("mittelfranken-fixture.DEU") for a in alerts)
    assert all(a.type == "GEWITTER" and a.level == "2" for a in alerts)


def test_a_missing_expires_is_tolerated() -> None:
    alerts = parse_cap_alerts(_fx("real_boeen_seewetter.xml"))
    assert alerts and alerts[0].valid_to is None


def test_malformed_xml_raises() -> None:
    with pytest.raises(DwdWarningsError):
        parse_cap_alerts(b"<alert>not closed")


# --- client (zip over a stubbed transport) -----------------------------


class _StubClient(DwdWarningsClient):
    def __init__(self, members: dict[str, bytes]) -> None:
        super().__init__("https://example.invalid/DISTRICT_DWD_STAT/")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        self._zip_bytes = buf.getvalue()
        self._fail = False

    def _get(self, url: str) -> bytes:
        if self._fail:
            raise DwdWarningsError("network down")
        if url.endswith("/"):
            return (
                b'<a href="Z_CAP_C_EDZW_20260901120000_PVW_STATUS_PREMIUMDWD_DISTRICT_DE.zip">x</a>'
            )
        return self._zip_bytes


def _members() -> dict[str, bytes]:
    return {
        "a.xml": _fx("mittelfranken_multi_area.xml"),
        "b.xml": _fx("real_sturmboeen_alert.xml"),
        "c.xml": _fx("cancelled.xml"),
        "readme.txt": b"ignore me",
    }


def test_fetch_alerts_unzips_parses_and_filters_by_warncell() -> None:
    client = _StubClient(_members())
    everything = client.fetch_alerts()
    assert len(everything) == 4  # 3 Mittelfranken areas + 1 Harz; the cancel drops out

    just_nbg_fue = client.fetch_alerts(warncell_ids={"109564000", "109563000"})
    assert {a.region for a in just_nbg_fue} == {"Stadt Nürnberg", "Stadt Fürth"}


def test_a_transport_failure_raises_dwd_warnings_error() -> None:
    client = _StubClient(_members())
    client._fail = True
    with pytest.raises(DwdWarningsError):
        client.fetch_alerts()


# --- adapter -----------------------------------------------------------


async def test_get_warnings_returns_e18_06_item_dicts_filtered_to_config() -> None:
    provider = build({"places": [{"name": "Nürnberg"}]})  # -> warncell 109564000 + 109574000
    provider._warnings_client = _StubClient(_members())  # type: ignore[attr-defined]

    items = await provider.get_warnings(region="mittelfranken")
    assert len(items) == 1
    it = items[0]
    assert it["region"] == "Stadt Nürnberg" and it["type"] == "GEWITTER"
    assert it["level"] == "2" and it["source_ref"].endswith("mittelfranken-fixture.DEU")
    assert it["valid_from"].endswith("+00:00") and set(it) >= {
        "region",
        "type",
        "level",
        "valid_from",
        "valid_to",
        "headline",
        "description",
        "source_ref",
    }


async def test_get_warnings_propagates_a_feed_failure() -> None:
    provider = build({})
    stub = _StubClient(_members())
    stub._fail = True
    provider._warnings_client = stub  # type: ignore[attr-defined]
    with pytest.raises(DwdWarningsError):
        await provider.get_warnings(region="mittelfranken")
