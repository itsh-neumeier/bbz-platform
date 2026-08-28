from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from bbz_core.api.idempotency import CommandEnvelope


def test_envelope_requires_command_id() -> None:
    with pytest.raises(ValidationError):
        CommandEnvelope()  # type: ignore[call-arg]


def test_envelope_roundtrip() -> None:
    cid = uuid.uuid4()
    env = CommandEnvelope(command_id=cid, expected_version=7, workplace_id="WP-1")
    assert env.command_id == cid
    assert env.expected_version == 7
    assert env.offline is False


def test_offline_flag() -> None:
    env = CommandEnvelope(command_id=uuid.uuid4(), offline=True)
    assert env.offline is True
