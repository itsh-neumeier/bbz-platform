from __future__ import annotations

import pytest

from bbz_integration_sdk.manifest import ManifestError, manifest_schema, validate_manifest


def _valid() -> dict[str, object]:
    return {
        "id": "telephony_mock",
        "name": "Telephony Mock",
        "version": "0.0.0",
        "domain": "telephony",
        "adapter": "integrations.telephony_mock.adapter:MockTelephonyProvider",
        "capabilities": ["call.answer", "call.hangup"],
        "mock": True,
    }


def test_schema_is_loadable() -> None:
    schema = manifest_schema()
    assert schema["title"] == "BBZ Integration Manifest"
    assert "id" in schema["required"]


def test_valid_manifest_parses() -> None:
    m = validate_manifest(_valid())
    assert m.id == "telephony_mock"
    assert m.domain == "telephony"
    assert m.mock is True


@pytest.mark.parametrize(
    "mutation",
    [
        {"id": "Telephony-Mock"},  # invalid pattern
        {"id": ""},  # empty
        {"domain": "Telephony"},  # uppercase
        {"version": None},
        {"extra_field": "nope"},  # additionalProperties: false
    ],
)
def test_invalid_manifest_rejected(mutation: dict[str, object]) -> None:
    raw = _valid() | mutation
    with pytest.raises(ManifestError):
        validate_manifest(raw)


def test_missing_required_field_rejected() -> None:
    raw = _valid()
    del raw["adapter"]
    with pytest.raises(ManifestError):
        validate_manifest(raw)
