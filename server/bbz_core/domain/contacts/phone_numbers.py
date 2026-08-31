r"""E.164 normalization for German fixed / mobile numbers and PBX extensions.

Roadmap E14-04. No external phone-number library — the BBZ runs a known,
DE-centric telephony estate (section 13.9), so a small explicit rule set is
safer and fully testable. Rules (region ``DE``):

* ``+49...``                   -> already international, cleaned only;
* ``00<cc>...``                -> ``+<cc>...`` (German international call prefix);
* ``0<area><subscriber>``      -> ``+49<area><subscriber>`` (national trunk ``0``);
* a bare 2-6 digit string      -> an internal PBX **extension**, not an E.164
  number: ``e164`` is ``None`` and the digits land in ``NumberParts.extension``
  (Epic 15's matcher resolves extensions with site context; this service does
  not);
* anything else (a 7+ digit block with no prefix, letters, empty) -> no match:
  ``e164`` and ``extension`` are both ``None``.

``e164`` is always either ``None`` or a string matching ``^\+[1-9]\d{1,14}$``.
The function never raises and never guesses a country code for an unprefixed
subscriber number — an ambiguous input is reported as "no match",
deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_REGION = "DE"

#: region -> (country code, national trunk prefix, international call prefix)
_REGIONS: dict[str, tuple[str, str, str]] = {
    "DE": ("49", "0", "00"),
}

_SEPARATORS = re.compile(r"[\s()/.\-]")
_DIGITS = re.compile(r"^\d+$")

#: a bare digit block up to this length is read as an internal extension
_MAX_EXTENSION_LEN = 6
#: the smallest digit count (after the ``+``) we accept as a real subscriber
#: number — rejects country-code-only fragments like ``+49``
_MIN_E164_DIGITS = 8
_E164 = re.compile(rf"^\+[1-9]\d{{{_MIN_E164_DIGITS - 1},14}}$")


@dataclass(frozen=True)
class NumberParts:
    raw: str
    #: the normalized international number, or ``None`` when it is not one
    e164: str | None
    #: an internal PBX extension when the input was a short bare digit block
    extension: str | None

    @property
    def is_e164(self) -> bool:
        return self.e164 is not None


def _valid(candidate: str) -> str | None:
    return candidate if _E164.match(candidate) else None


def _clean(raw: str) -> str:
    s = (raw or "").strip()
    if s[:4].lower() == "tel:":
        s = s[4:]
    return _SEPARATORS.sub("", s)


def normalize_number(raw: str, *, region: str = DEFAULT_REGION) -> NumberParts:
    country_code, trunk, intl = _REGIONS.get(region, _REGIONS[DEFAULT_REGION])
    cleaned = _clean(raw)

    if cleaned.startswith("+"):
        return NumberParts(raw=raw, e164=_valid(cleaned), extension=None)

    if not cleaned or not _DIGITS.match(cleaned):
        return NumberParts(raw=raw, e164=None, extension=None)

    if cleaned.startswith(intl):
        return NumberParts(raw=raw, e164=_valid("+" + cleaned[len(intl) :]), extension=None)

    if cleaned.startswith(trunk):
        return NumberParts(
            raw=raw, e164=_valid("+" + country_code + cleaned[len(trunk) :]), extension=None
        )

    if len(cleaned) <= _MAX_EXTENSION_LEN:
        return NumberParts(raw=raw, e164=None, extension=cleaned)

    # a long unprefixed block — we will not guess a country code for it
    return NumberParts(raw=raw, e164=None, extension=None)
