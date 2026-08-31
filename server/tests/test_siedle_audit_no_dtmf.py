"""E17-06: the DTMF plaintext lands in NO sink — audit, domain event, outbox
result, structured log — only the profile id. `bbz_core.redaction` is the net:
a transient `redacting(<code>)` context masks the value everywhere, so even a
provider that echoes the code in an error message cannot leak it.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import structlog
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.repositories.door_action_profiles import DoorActionProfileService
from bbz_core.infra.repositories.door_open import DoorOpenService
from bbz_core.integrations_host.providers import active_telephony_provider, reset_provider_cache
from bbz_core.redaction import MASK, active_secret_count, redacting, scrub

#: a distinctive sentinel — valid DTMF alphabet, unlikely to collide with a uuid
_SENTINEL = "9A9A9A#9A"


# --- unit: the redaction primitive -----------------------------------------


def test_scrub_is_a_passthrough_when_nothing_is_registered() -> None:
    payload = {"a": f"the code is {_SENTINEL}", "b": [1, _SENTINEL]}
    assert scrub(payload) is payload
    assert active_secret_count() == 0


def test_redacting_masks_every_string_leaf_then_resets() -> None:
    with redacting(_SENTINEL):
        assert active_secret_count() == 1
        out = scrub({"x": f"tone {_SENTINEL}!", "y": ["ok", {"z": _SENTINEL}], "n": 5})
        assert _SENTINEL not in str(out)
        assert out["x"] == f"tone {MASK}!"
        assert out["y"][1]["z"] == MASK
        assert out["n"] == 5
    assert active_secret_count() == 0


def test_too_short_or_empty_secrets_are_ignored() -> None:
    with redacting("", "x", None):
        assert active_secret_count() == 0
        assert scrub(f"keep {_SENTINEL}") == f"keep {_SENTINEL}"


def test_the_structlog_processor_masks_a_registered_secret() -> None:
    from bbz_core.logging import _redact

    buf = io.StringIO()
    logger = structlog.wrap_logger(
        structlog.PrintLogger(buf),
        processors=[_redact, structlog.processors.JSONRenderer()],
    )
    with redacting(_SENTINEL):
        logger.warning("provider_error", detail=f"bad tone {_SENTINEL} rejected")
    masked = buf.getvalue()
    assert _SENTINEL not in masked and MASK in masked

    buf.seek(0)
    buf.truncate()
    logger.warning("later", detail=f"unrelated {_SENTINEL}")  # nothing registered now
    assert _SENTINEL in buf.getvalue()


# --- integration: a full door-open with a code-leaking provider ------------


@pytest.fixture(autouse=True)
def _door_key() -> Iterator[None]:
    os.environ["BBZ_DOOR_DTMF_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    yield
    os.environ.pop("BBZ_DOOR_DTMF_ENCRYPTION_KEY", None)


@pytest.fixture(autouse=True)
def _clean_provider_cache() -> Iterator[None]:
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _make_user(s: AsyncSession) -> uuid.UUID:
    from bbz_core.infra.models.identity import User

    await s.rollback()
    async with s.begin():
        u = User(display_name="Op")
        s.add(u)
        await s.flush()
        return u.id


async def _door(s: AsyncSession) -> uuid.UUID:
    profile = await DoorActionProfileService(s).create(
        name="Haupttor", dtmf_code=_SENTINEL, post_dtmf_delay_ms=0, auto_hangup=True, actor_id=None
    )
    await s.rollback()
    async with s.begin():
        ep = TechnicalEndpoint(
            name="Klingel",
            type="door_station",
            dtmf_profile_id=profile.id,
            door_open_timeout_seconds=3,
        )
        s.add(ep)
        await s.flush()
        return ep.id


async def test_a_provider_that_echoes_the_code_still_leaks_it_to_no_sink(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await _make_user(s)
    endpoint_id = await _door(s)
    provider = await active_telephony_provider()
    call_id = provider.simulate_incoming(from_number="+49110", to_line="1001")  # type: ignore[attr-defined]

    async def _leaky_send_dtmf(*, call_id: str, dtmf: str, command_id: str) -> Any:
        raise RuntimeError(f"gateway rejected tone sequence {dtmf}")

    monkeypatch.setattr(provider, "send_dtmf", _leaky_send_dtmf)

    result = await DoorOpenService(s).open(
        endpoint_id=endpoint_id, call_id=call_id, command_id=uuid.uuid4(), actor_id=actor
    )
    assert result.outcome == "provider_error"
    assert _SENTINEL not in result.detail and MASK in result.detail

    await s.rollback()
    audits = (await s.execute(select(AuditEvent))).scalars().all()
    events = (await s.execute(select(DomainEvent))).scalars().all()
    outbox = (await s.execute(select(ExternalActionOutbox))).scalars().all()

    for a in audits:
        assert _SENTINEL not in f"{a.action}{a.before}{a.after}{a.reason}"
    for e in events:
        assert _SENTINEL not in str(e.payload)
    for o in outbox:
        assert _SENTINEL not in f"{o.payload}{o.result}{o.last_error}"

    # the profile IS referenced — a redaction that also drops the id would be a bug
    res = next(a for a in audits if a.action == "DOOR_OPEN_RESULT")
    assert res.after["door_action_profile_id"] is not None
    assert res.after["outcome"] == "provider_error"


async def test_a_clean_open_never_writes_the_code_anywhere(s: AsyncSession) -> None:
    actor = await _make_user(s)
    endpoint_id = await _door(s)
    provider = await active_telephony_provider()
    call_id = provider.simulate_incoming(from_number="+49110", to_line="1001")  # type: ignore[attr-defined]

    result = await DoorOpenService(s).open(
        endpoint_id=endpoint_id, call_id=call_id, command_id=uuid.uuid4(), actor_id=actor
    )
    assert result.outcome == "opened"

    await s.rollback()
    for a in (await s.execute(select(AuditEvent))).scalars().all():
        assert _SENTINEL not in f"{a.before}{a.after}{a.reason}"
    for o in (await s.execute(select(ExternalActionOutbox))).scalars().all():
        assert _SENTINEL not in f"{o.payload}{o.result}{o.last_error}"
    assert active_secret_count() == 0  # context cleaned up
