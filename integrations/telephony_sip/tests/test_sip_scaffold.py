"""telephony_sip scaffold: manifest validates, provider is protocol-conformant,
control commands are gated until the SIP stack lands (E13-01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbz_integration_sdk.manifest import validate_manifest
from bbz_integration_sdk.providers import TELEPHONY_METHODS, Provider, TelephonyProvider
from bbz_integration_sdk.providers.telephony_types import (
    CallerResolution,
    LineInfo,
    ReconcileResult,
)
from integrations.telephony_sip.adapter import (
    SipNotConfiguredError,
    SipTelephonyProvider,
    build,
)

_DIR = Path(__file__).resolve().parents[1]


def test_manifest_validates_against_the_schema() -> None:
    raw = json.loads((_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = validate_manifest(raw)
    assert manifest.id == "telephony_sip"
    assert manifest.domain == "telephony"
    assert manifest.mock is False
    assert manifest.adapter == "integrations.telephony_sip.adapter:SipTelephonyProvider"


def test_config_schema_is_valid_json_schema() -> None:
    import jsonschema

    schema = json.loads((_DIR / "config_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    # a minimal valid config
    jsonschema.validate({"gateway": {"kind": "asterisk_ari", "host": "pbx.local"}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"gateway": {"kind": "cisco"}}, schema)  # not an allowed kind


def test_adapter_satisfies_the_telephony_protocol() -> None:
    p = SipTelephonyProvider()
    assert isinstance(p, TelephonyProvider)
    assert isinstance(p, Provider)
    for name in TELEPHONY_METHODS:
        assert callable(getattr(p, name))


async def test_lifecycle_and_read_queries_are_safe_defaults() -> None:
    p = build({"lines": ["2001"]})
    await p.initialize()

    assert p.info().integration_id == "telephony_sip"
    assert p.info().mock is False
    health = await p.health()
    assert health.state.value == "unknown"
    assert "scaffold" in health.summary  # no gateway block → still a scaffold

    assert [line.line_id for line in await p.list_lines()] == ["2001"]
    assert isinstance(await p.get_line_state("2001"), LineInfo)
    assert (await p.get_line_state("nope")).state.value == "unknown"
    assert await p.get_active_calls() == []
    assert isinstance(await p.reconcile(), ReconcileResult)

    res = await p.resolve_caller(number="+49911500")
    assert isinstance(res, CallerResolution) and res.matched is False

    stream = p.subscribe_call_events()
    with pytest.raises(StopAsyncIteration):
        await anext(stream)

    await p.shutdown()


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.dial(line_id="1", destination="2", command_id="c"),
        lambda p: p.answer(call_id="x", command_id="c"),
        lambda p: p.hangup(call_id="x", command_id="c"),
        lambda p: p.hold(call_id="x", command_id="c"),
        lambda p: p.resume(call_id="x", command_id="c"),
        lambda p: p.transfer(call_id="x", destination="9", command_id="c"),
        lambda p: p.conference(call_ids=["x"], command_id="c"),
        lambda p: p.send_dtmf(call_id="x", dtmf="12#", command_id="c"),
    ],
)
async def test_control_commands_are_gated_until_the_sip_stack_lands(call: object) -> None:
    p = SipTelephonyProvider()
    with pytest.raises(SipNotConfiguredError):
        await call(p)  # type: ignore[operator]
