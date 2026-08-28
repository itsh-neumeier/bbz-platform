from __future__ import annotations

import pytest

from bbz_integration_sdk.providers import MonitorProvider
from integrations.monitor_mock.adapter import LOCKED_INPUT, LOCKED_OUTPUT, MockMonitorProvider


def test_satisfies_protocol() -> None:
    assert isinstance(MockMonitorProvider(), MonitorProvider)


async def test_route_and_readback() -> None:
    p = MockMonitorProvider()
    await p.set_route(output_id="AP2", input_id="CODA1", command_id="c1")
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes["AP2"] == "CODA1"


async def test_lower_left_is_locked_to_bbz_os() -> None:
    p = MockMonitorProvider()
    with pytest.raises(ValueError):
        await p.set_route(output_id=LOCKED_OUTPUT, input_id="BKU1", command_id="c1")
    routes = {r["output_id"]: r["input_id"] for r in await p.get_routes()}
    assert routes[LOCKED_OUTPUT] == LOCKED_INPUT
