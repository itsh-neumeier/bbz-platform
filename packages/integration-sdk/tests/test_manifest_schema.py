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


def test_capability_groups_and_legacy_alias_parse() -> None:
    raw = _valid() | {
        "capabilities": ["call.answer", "call.hangup", "call.dial"],
        "capability_groups": {"basic": ["call.answer", "call.hangup"], "outbound": ["call.dial"]},
        "legacy_display_alias": "OldName",
    }
    m = validate_manifest(raw)
    assert m.capability_groups == {
        "basic": ["call.answer", "call.hangup"],
        "outbound": ["call.dial"],
    }
    assert m.legacy_display_alias == "OldName"


def test_capability_group_referencing_an_undeclared_capability_is_rejected() -> None:
    raw = _valid() | {"capability_groups": {"basic": ["call.transfer"]}}  # not in capabilities
    with pytest.raises(ManifestError, match="not in `capabilities`"):
        validate_manifest(raw)


def test_pending_vendor_documentation_marker_parses() -> None:
    assert validate_manifest(_valid()).pending_vendor_documentation == []  # default

    m2 = validate_manifest(_valid() | {"pending_vendor_documentation": ["api-endpoints", "auth"]})
    assert m2.pending_vendor_documentation == ["api-endpoints", "auth"]


def test_coda_video_manifest_carries_the_blocker_marker_while_mock() -> None:
    """E16-13: the shipped coda_video manifest declares the vendor-docs blocker
    for as long as it is a mock (ADR-0006)."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    raw = json.loads((root / "integrations" / "coda_video" / "manifest.json").read_text("utf-8"))
    m = validate_manifest(raw)
    assert m.mock is True
    assert m.pending_vendor_documentation, "coda_video must declare pending_vendor_documentation"
    assert {"api-endpoints", "authentication", "sdk-classes"} <= set(m.pending_vendor_documentation)
