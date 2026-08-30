"""The stateless two-step reactivation confirm token (E20-05)."""

from __future__ import annotations

import os
import uuid

import pytest

from bbz_core.api.reactivation import ReactivationTokenError, mint_token, verify_token


@pytest.fixture(autouse=True)
def _secret() -> None:
    os.environ["BBZ_JWT_SECRET"] = "reactivation-token-test-secret-at-least-32b!"


def test_mint_then_verify_round_trips() -> None:
    ev, user = uuid.uuid4(), uuid.uuid4()
    token, expiry = mint_token(ev, user, 7, now=1_000.0)
    assert expiry > 1_000
    verify_token(token, ev, user, 7, now=1_050.0)  # does not raise


def test_expired_token_is_rejected() -> None:
    ev, user = uuid.uuid4(), uuid.uuid4()
    token, expiry = mint_token(ev, user, 1, now=1_000.0)
    with pytest.raises(ReactivationTokenError, match="expired"):
        verify_token(token, ev, user, 1, now=expiry + 1)


def test_token_is_bound_to_event_user_and_version() -> None:
    ev, user = uuid.uuid4(), uuid.uuid4()
    token, _ = mint_token(ev, user, 3, now=1_000.0)
    with pytest.raises(ReactivationTokenError):
        verify_token(token, uuid.uuid4(), user, 3, now=1_010.0)  # other event
    with pytest.raises(ReactivationTokenError):
        verify_token(token, ev, uuid.uuid4(), 3, now=1_010.0)  # other user
    with pytest.raises(ReactivationTokenError):
        verify_token(token, ev, user, 4, now=1_010.0)  # other version


def test_tampered_signature_is_rejected() -> None:
    ev, user = uuid.uuid4(), uuid.uuid4()
    token, _ = mint_token(ev, user, 2, now=1_000.0)
    body, _sig = token.split(".", 1)
    forged = f"{body}.{'A' * len(_sig)}"
    with pytest.raises(ReactivationTokenError, match="signature"):
        verify_token(forged, ev, user, 2, now=1_010.0)


@pytest.mark.parametrize("bad", ["", "nodot", "a.b.c", "!!!.???"])
def test_malformed_tokens_are_rejected(bad: str) -> None:
    with pytest.raises(ReactivationTokenError):
        verify_token(bad, uuid.uuid4(), uuid.uuid4(), 1, now=1.0)


def test_a_different_secret_invalidates_the_token() -> None:
    ev, user = uuid.uuid4(), uuid.uuid4()
    token, _ = mint_token(ev, user, 1, now=1_000.0)
    os.environ["BBZ_JWT_SECRET"] = "a-completely-different-secret-at-least-32-b!"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    with pytest.raises(ReactivationTokenError):
        verify_token(token, ev, user, 1, now=1_010.0)
    settings_mod.get_settings.cache_clear()
