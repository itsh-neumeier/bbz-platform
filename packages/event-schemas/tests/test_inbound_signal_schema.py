"""inbound_signal.v1.json — the normalized inbound signal shape (E15-04)."""

from __future__ import annotations

from datetime import UTC, datetime

import jsonschema
import pytest

from bbz_event_schemas import inbound_signal_schema


def _base() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "signal_type": "BMA_ALARM_CALL",
        "provider": "telephony_cucm",
        "occurred_at": now,
        "received_at": now,
        "gateway_node": "BBZ-SRV01",
        "source": {"dnis": "110", "cti_route_point": "RP_BMA", "severity": "critical"},
    }


def test_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(inbound_signal_schema())


def test_a_minimal_signal_validates() -> None:
    jsonschema.validate(_base(), inbound_signal_schema())


def test_a_vendor_field_at_the_top_level_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**_base(), "cisco_call_handle": "0xABCD"}, inbound_signal_schema())


def test_a_vendor_field_in_source_is_rejected() -> None:
    bad = _base()
    bad["source"] = {**bad["source"], "coda_zone": "west"}  # type: ignore[dict-item]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, inbound_signal_schema())


@pytest.mark.parametrize(
    "st",
    [
        "CALL_RINGING",
        "CALL_ANSWERED",
        "CALL_ENDED",
        "TECHNICAL_ALARM_RAISED",
        "PANIC_ALARM_RAISED",
        "DOORBELL_RINGING",
        "BMA_ALARM_CALL",
    ],
)
def test_every_declared_signal_type_validates(st: str) -> None:
    jsonschema.validate({**_base(), "signal_type": st}, inbound_signal_schema())


def test_an_unknown_signal_type_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**_base(), "signal_type": "ALIEN_INVASION"}, inbound_signal_schema())


def test_severity_and_direction_are_constrained() -> None:
    bad = _base()
    bad["source"] = {"severity": "apocalyptic"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, inbound_signal_schema())
