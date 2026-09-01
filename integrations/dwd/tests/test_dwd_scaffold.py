"""dwd scaffold (E18-01): manifest validates, config schema is sane, the adapter
is a protocol-conformant WeatherProvider, lifecycle is safe. Warnings are live
(E18-02, see test_dwd_warnings.py); radar / observations still gated (E18-03/04)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.manifest import validate_manifest
from bbz_integration_sdk.providers import Provider, WeatherProvider
from integrations.dwd.adapter import (
    DEFAULT_PLACES,
    DwdNotImplementedError,
    DwdWeatherProvider,
    build,
)

_DIR = Path(__file__).resolve().parents[1]


def test_manifest_validates_and_declares_three_weather_capability_groups() -> None:
    raw = json.loads((_DIR / "manifest.json").read_text(encoding="utf-8"))
    m = validate_manifest(raw)
    assert m.id == "dwd" and m.domain == "weather" and m.mock is False
    assert set(m.capabilities) == {"weather.warnings", "weather.radar", "weather.observations"}
    assert set(m.capability_groups) == {"warnings", "radar", "observations"}
    assert m.pending_vendor_documentation == []  # DWD open data is documented (ADR-0026)


def test_config_schema_is_valid_and_accepts_the_mittelfranken_shape() -> None:
    schema = json.loads((_DIR / "config_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate({}, schema)
    jsonschema.validate(
        {
            "region": "mittelfranken",
            "enabled_capabilities": ["weather.warnings"],
            "places": [{"name": "Nürnberg", "warncell_id": "809135100", "poi_station_id": "10763"}],
            "radar": {"frame_count": 6},
        },
        schema,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"enabled_capabilities": ["weather.tides"]}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"places": [{"warncell_id": "x"}]}, schema)  # name is required


def test_adapter_satisfies_the_weather_protocol() -> None:
    p = DwdWeatherProvider()
    assert isinstance(p, WeatherProvider)
    assert isinstance(p, Provider)


async def test_lifecycle_defaults_to_mittelfranken_and_reports_scaffold_health() -> None:
    p = build({})
    await p.initialize()

    assert p.info().integration_id == "dwd" and p.info().mock is False
    assert p.capabilities().has(Capability.WEATHER_WARNINGS)
    assert p.capabilities().has(Capability.WEATHER_RADAR)
    assert p.capabilities().has(Capability.WEATHER_OBSERVATIONS)

    h = await p.health()
    assert h.state.value == "healthy" and "warnings + observations live" in h.summary
    assert "E18-03" in h.summary  # radar still pending
    assert h.details["places"] == len(DEFAULT_PLACES)
    assert h.details["warncells"] >= len(DEFAULT_PLACES)  # bundled mittelfranken.json
    assert h.details["poi_stations"] >= 1
    assert h.details["attribution"] == "Deutscher Wetterdienst"

    await p.shutdown()
    assert (await p.health()).state.value == "disabled"


async def test_enabled_capabilities_narrows_the_capability_set() -> None:
    p = build({"enabled_capabilities": ["weather.warnings"]})
    assert p.capabilities().has(Capability.WEATHER_WARNINGS)
    assert not p.capabilities().has(Capability.WEATHER_RADAR)


async def test_configured_places_replace_the_defaults_and_keep_bundled_warncells() -> None:
    p = build({"places": [{"name": "Nürnberg"}]})  # resolved from mittelfranken.json
    h = await p.health()
    assert h.details["places"] == 1 and h.details["warncells"] >= 1


async def test_a_configured_place_may_carry_its_own_warncell() -> None:
    p = build({"places": [{"name": "Passau", "warncell_id": "109275000"}]})
    assert (await p.health()).details["warncells"] == 1


async def test_radar_is_gated_until_its_adapter_epic() -> None:
    p = build({})
    with pytest.raises(DwdNotImplementedError):
        await p.get_radar_frames(area="mittelfranken")
