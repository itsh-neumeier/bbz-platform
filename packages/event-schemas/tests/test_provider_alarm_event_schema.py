"""provider_alarm_event.v1.json -- the immutable normalized alarm event (E16-04)."""

from __future__ import annotations

from datetime import UTC, datetime

import jsonschema
import pytest

from bbz_event_schemas import provider_alarm_event_schema


def _base() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "provider": "coda_video",
        "provider_event_id": "CODA-EVT-4711",
        "provider_instance_id": "coda-mock-1",
        "alarm_type": "panic",
        "source_external_id": "CODA-ALARM-4711",
        "received_at": now,
        "raw_hash": "a" * 64,
    }


def test_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(provider_alarm_event_schema())


def test_a_minimal_event_validates() -> None:
    jsonschema.validate(_base(), provider_alarm_event_schema())


def test_a_full_event_validates() -> None:
    now = datetime.now(UTC).isoformat()
    jsonschema.validate(
        {
            **_base(),
            "provider_alarm_id": "ALM-9",
            "alarm_subtype": "panic_button",
            "source_name": "SP Nbg",
            "site_external_id": "Nuernberg Hbf",
            "occurred_at": now,
            "severity_external": "Sehr hoch",
            "state_external": "active",
            "associated_camera_ids": ["CAM-1", "CAM-2"],
        },
        provider_alarm_event_schema(),
    )


def test_a_raw_vendor_payload_field_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**_base(), "raw": {"vendor": "stuff"}}, provider_alarm_event_schema())


def test_a_missing_mandatory_field_is_rejected() -> None:
    bad = _base()
    del bad["source_external_id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, provider_alarm_event_schema())


def test_raw_hash_must_be_bare_sha256_hex() -> None:
    for bad in ("sha256:" + "a" * 64, "a" * 63, "A" * 64, "xyz"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**_base(), "raw_hash": bad}, provider_alarm_event_schema())


def test_associated_camera_ids_must_be_unique() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**_base(), "associated_camera_ids": ["CAM-1", "CAM-1"]},
            provider_alarm_event_schema(),
        )
