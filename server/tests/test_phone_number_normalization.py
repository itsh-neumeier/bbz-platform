"""E.164 normalization matrix (E14-04) — pure, no database."""

from __future__ import annotations

import re

import pytest

from bbz_core.domain.contacts import normalize_number

# raw input -> expected e164 (None = not an international number)
_E164_CASES = [
    # already international, just formatting to strip
    ("+49911500123", "+49911500123"),
    ("+49 911 500 123", "+49911500123"),
    ("+49 (911) 500-123", "+49911500123"),
    ("tel:+49911500123", "+49911500123"),
    ("  +49 911 500123  ", "+49911500123"),
    # German international call prefix 00
    ("0049911500123", "+49911500123"),
    ("00 49 911 500 123", "+49911500123"),
    # national trunk 0
    ("0911500123", "+49911500123"),
    ("0911 / 500 123", "+49911500123"),
    ("030 12345678", "+493012345678"),
    ("0170 1234567", "+491701234567"),
    # a foreign number stays as given
    ("+1 (212) 555-0199", "+12125550199"),
    ("+41 44 500 12 34", "+41445001234"),
    # not resolvable to an international number
    ("", None),
    ("   ", None),
    ("0", None),
    ("+49", None),
    ("+49301", None),  # country-code-only fragment — too short
    ("911500123", None),  # 9 bare digits, no prefix — we do not guess a CC
    ("Reception", None),
    ("+49-abc-123", None),
]


@pytest.mark.parametrize(("raw", "expected"), _E164_CASES)
def test_normalize_to_e164(raw: str, expected: str | None) -> None:
    assert normalize_number(raw).e164 == expected


@pytest.mark.parametrize("raw", ["42", "4711", "12", "820", "99"])
def test_short_bare_digits_are_read_as_a_pbx_extension(raw: str) -> None:
    parts = normalize_number(raw)
    assert parts.e164 is None
    assert parts.extension == raw
    assert parts.is_e164 is False


def test_a_seven_digit_block_is_neither_a_number_nor_an_extension() -> None:
    parts = normalize_number("1234567")
    assert parts.e164 is None and parts.extension is None


def test_every_e164_result_matches_the_canonical_shape() -> None:
    canon = re.compile(r"^\+[1-9]\d{7,14}$")
    for raw, expected in _E164_CASES:
        if expected is not None:
            assert canon.match(normalize_number(raw).e164 or "")


def test_output_is_deterministic() -> None:
    a, b = normalize_number("0911500123"), normalize_number("0911 500 123")
    assert a.e164 == b.e164 == "+49911500123"


def test_region_is_pluggable_and_falls_back_to_de() -> None:
    assert normalize_number("0911500123", region="ZZ").e164 == "+49911500123"


def test_it_never_raises() -> None:
    for weird in ["", "+", "++49", "0" * 40, "  ", None]:  # type: ignore[list-item]
        normalize_number(weird)  # type: ignore[arg-type]
