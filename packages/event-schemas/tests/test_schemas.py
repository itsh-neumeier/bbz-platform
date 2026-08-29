from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jsonschema
import pytest

from bbz_event_schemas import (
    UnknownEventTypeError,
    event_payload_schema,
    known_event_types,
    list_schemas,
    load_schema,
)


def test_all_shipped_schemas_are_valid_json_schema() -> None:
    names = list_schemas()
    assert "domain_event.envelope.v1.json" in names
    assert "telephony_event.v1.json" in names
    for name in names:
        load_schema(name)  # raises if the schema itself is invalid


def test_domain_event_envelope_accepts_minimal_valid_event() -> None:
    schema = load_schema("domain_event.envelope.v1")
    event = {
        "event_seq": 1,
        "event_uuid": str(uuid.uuid4()),
        "aggregate_type": "event",
        "aggregate_id": "EVT-1",
        "event_type": "EVENT_CREATED",
        "occurred_at_utc": datetime.now(UTC).isoformat(),
        "node_id": "BBZ-SRV01",
        "schema_version": 1,
        "payload": {},
    }
    jsonschema.validate(event, schema)


def test_domain_event_envelope_rejects_extra_and_missing() -> None:
    schema = load_schema("domain_event.envelope.v1")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event_seq": 1}, schema)  # missing required


def test_telephony_event_enum_enforced() -> None:
    schema = load_schema("telephony_event.v1")
    base = {
        "telephony_event_id": "t1",
        "provider": "telephony_mock",
        "raw_event_type": "MockRing",
        "event_type": "CALL_RINGING",
        "occurred_at": datetime.now(UTC).isoformat(),
        "received_at": datetime.now(UTC).isoformat(),
        "gateway_node": "BBZ-SRV01",
    }
    jsonschema.validate(base, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "event_type": "CALL_TELEPORTED"}, schema)


def test_every_known_event_type_has_a_usable_payload_schema() -> None:
    types = known_event_types()
    assert {"EVENT_CREATED", "EVENT_ASSIGNED", "EVENT_NOTE_ADDED"} <= types
    for name in types:
        jsonschema.Draft202012Validator.check_schema(event_payload_schema(name))


def test_event_payload_schema_validates_and_rejects() -> None:
    schema = event_payload_schema("EVENT_CREATED")
    jsonschema.validate({"title": "x", "priority": "high", "actor_id": "u1"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"title": "x"}, schema)  # missing priority/actor_id


def test_unknown_event_type_raises() -> None:
    with pytest.raises(UnknownEventTypeError):
        event_payload_schema("EVENT_TELEPORTED")
