"""monitor_mock — the complete in-memory routing provider (roadmap E19-06)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.diagnostics import HealthState
from bbz_integration_sdk.manifest import validate_manifest
from bbz_integration_sdk.providers import MonitorProvider, Provider
from integrations.monitor_mock.adapter import (
    OutputUnreachableError,
    UnknownPortError,
    build,
)

_DIR = Path(__file__).resolve().parents[1]


def test_manifest_validates() -> None:
    m = validate_manifest(json.loads((_DIR / "manifest.json").read_text(encoding="utf-8")))
    assert m.domain == "monitor" and m.mock is True


def test_satisfies_the_sdk_protocol() -> None:
    p = build()
    assert isinstance(p, MonitorProvider)
    assert isinstance(p, Provider)


async def test_lists_the_catalog_ports() -> None:
    p = build()
    ins = {i["input_id"] for i in await p.list_inputs()}
    outs = {o["output_id"] for o in await p.list_outputs()}
    assert ins == {"bbz-os", "bku1", "bku2", "bku3", "bku4", "coda1", "coda2"}
    assert outs == {f"workplace{n}" for n in range(1, 7)} | {"large-display"}


async def test_route_is_applied_and_read_straight_back() -> None:
    p = build()
    await p.set_route(output_id="workplace2", input_id="coda1", command_id="c1")
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes["workplace2"] == "coda1"


async def test_an_unknown_port_is_rejected() -> None:
    p = build()
    with pytest.raises(UnknownPortError):
        await p.set_route(output_id="workplace9", input_id="bbz-os", command_id="c1")
    with pytest.raises(UnknownPortError):
        await p.set_route(output_id="workplace1", input_id="hdmi", command_id="c2")


async def test_a_repeated_command_id_is_not_applied_twice() -> None:
    p = build()
    first = await p.set_route(output_id="workplace1", input_id="bku1", command_id="cmd-42")
    # a second call with the same id — even with different args — replays the first
    again = await p.set_route(output_id="workplace1", input_id="bku2", command_id="cmd-42")
    assert again == first
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes["workplace1"] == "bku1"  # the bku2 call did nothing


async def test_an_unreachable_output_rejects_a_route_and_reports_degraded() -> None:
    p = build({"unreachable_outputs": ["workplace5"]})
    with pytest.raises(OutputUnreachableError):
        await p.set_route(output_id="workplace5", input_id="bku4", command_id="c1")
    assert not await p.get_routes()  # nothing applied

    h = await p.health()
    assert h.state == HealthState.DEGRADED and "workplace5" in h.details["unreachable"]


async def test_apply_layout_is_atomic() -> None:
    p = build({"unreachable_outputs": ["large-display"]})
    layout = {"workplace1": "bku1", "workplace2": "bku2", "large-display": "coda2"}
    with pytest.raises(OutputUnreachableError):
        await p.apply_layout(layout=layout, command_id="L1")
    assert not await p.get_routes()  # one bad output → nothing applied


async def test_apply_layout_applies_everything_then_is_idempotent() -> None:
    p = build()
    layout = {"workplace1": "bku1", "workplace4": "bbz-os", "large-display": "coda2"}
    r1 = await p.apply_layout(layout=layout, command_id="L1")
    assert set(r1["applied"]) == set(layout)
    r2 = await p.apply_layout(layout={"workplace1": "coda1"}, command_id="L1")
    assert r2 == r1
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes == layout


async def test_the_mock_does_not_enforce_bbz_policy() -> None:
    # the "lower-left is BBZ-OS" rule is the domain's job (E19-03), not the device
    p = build()
    await p.set_route(output_id="workplace4", input_id="bku1", command_id="c1")
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes["workplace4"] == "bku1"


def test_capabilities() -> None:
    caps = build().capabilities()
    assert caps.has(Capability.MONITOR_ROUTE) and caps.has(Capability.MONITOR_LAYOUT_PROFILES)
