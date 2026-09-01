"""monitor_weytec scaffold (roadmap E19-07): the manifest validates, the adapter
is protocol-shaped and honestly labelled, and every routing call raises — the
Weytec API must not be invented (MASTER_PROMPT §9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.diagnostics import HealthState
from bbz_integration_sdk.manifest import validate_manifest
from bbz_integration_sdk.providers import MonitorProvider, Provider
from integrations.monitor_weytec.adapter import (
    WeytecMonitorProvider,
    WeytecNotConfiguredError,
    build,
)

_DIR = Path(__file__).resolve().parents[1]


def test_manifest_validates_and_is_marked_pending() -> None:
    m = validate_manifest(json.loads((_DIR / "manifest.json").read_text(encoding="utf-8")))
    assert m.id == "monitor_weytec" and m.domain == "monitor"
    assert m.mock is False
    assert m.capabilities == []  # nothing usable yet
    raw = json.loads((_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert raw["pending_vendor_documentation"]  # the machine-readable blocker marker


def test_config_schema_is_valid_json_schema() -> None:
    import jsonschema

    schema = json.loads((_DIR / "config_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate({"instance_id": "weytec-1"}, schema)


def test_the_adapter_is_protocol_shaped() -> None:
    p = build()
    assert isinstance(p, MonitorProvider)
    assert isinstance(p, Provider)
    assert isinstance(p, WeytecMonitorProvider)


async def test_lifecycle_is_honest_but_nothing_is_usable() -> None:
    p = build()
    await p.initialize()
    assert p.info().integration_id == "monitor_weytec" and p.info().mock is False
    assert list(p.capabilities()) == []
    h = await p.health()
    assert h.state == HealthState.DISABLED
    assert "pending" in h.summary.lower()
    await p.shutdown()


async def test_every_routing_call_raises() -> None:
    p = build()
    with pytest.raises(WeytecNotConfiguredError):
        await p.list_inputs()
    with pytest.raises(WeytecNotConfiguredError):
        await p.list_outputs()
    with pytest.raises(WeytecNotConfiguredError):
        await p.get_routes()
    with pytest.raises(WeytecNotConfiguredError):
        await p.set_route(output_id="workplace1", input_id="bbz-os", command_id="c1")
    with pytest.raises(WeytecNotConfiguredError):
        await p.apply_layout(layout={"workplace1": "bbz-os"}, command_id="c1")
    # it is a NotImplementedError so a generic caller catches it too
    assert issubclass(WeytecNotConfiguredError, NotImplementedError)


def test_the_blocker_doc_exists_and_is_referenced() -> None:
    doc = _DIR.parents[1] / "docs" / "integrations" / "weytec-monitor-pending.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "BLOCKED" in text and "must not be invented" in text
    readme = (_DIR / "README.md").read_text(encoding="utf-8")
    assert "weytec-monitor-pending.md" in readme
