"""Caller resolution: an incoming phone number -> contact + priority (E14-04).

The number is first normalized to E.164
(:func:`bbz_core.domain.contacts.normalize_number`), then matched against the
``contact_numbers`` of **live** contacts:

1. exact E.164 match;
2. the query is a stored number plus a short direct-dial extension
   (stored number is a prefix, 1..6 extra digits);
3. one number is a digit-suffix of the other (a safety net for stored numbers
   that omit the country or area code).

The longest match wins; a tie across **different** contacts is reported as
ambiguous and resolves to "unknown" — the service never guesses. A short
per-process TTL cache keeps the per-call cost negligible and self-heals within
:data:`_CACHE_TTL`; :func:`clear_matcher_cache` drops it (used by tests).

E11-08 (caller resolution on an inbound call) is the caller. Epic 15 has its own
matcher for technical endpoints / PBX extensions.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.contacts import normalize_number
from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority

_MIN_MATCH_DIGITS = 7
_MAX_EXTENSION_DIGITS = 6
_CACHE_TTL = 30.0


@dataclass(frozen=True)
class CallerMatch:
    #: the normalized incoming number, or ``None`` if it could not be normalized
    e164: str | None
    contact_id: uuid.UUID | None = None
    name: str | None = None
    priority: str | None = None
    #: the stored ``contact_numbers.e164`` the match was made on
    matched_on: str | None = None
    #: an internal PBX extension when the input was a bare short digit block
    extension: str | None = None
    #: true when the number matched more than one contact (-> treated as unknown)
    ambiguous: bool = False

    @property
    def matched(self) -> bool:
        return self.contact_id is not None


_cache: dict[str, tuple[float, CallerMatch]] = {}


def clear_matcher_cache() -> None:
    _cache.clear()


def _common_suffix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(reversed(a), reversed(b), strict=False):
        if x != y:
            break
        n += 1
    return n


def _score(query_digits: str, stored_digits: str) -> int:
    """How strongly ``stored_digits`` identifies ``query_digits`` (0 = no match)."""
    if query_digits == stored_digits:
        return len(stored_digits)
    # stored number + a short direct-dial extension
    if (
        query_digits.startswith(stored_digits)
        and 1 <= len(query_digits) - len(stored_digits) <= _MAX_EXTENSION_DIGITS
        and len(stored_digits) >= _MIN_MATCH_DIGITS
    ):
        return len(stored_digits)
    # one number is a digit-suffix of the other (missing country / area code)
    k = _common_suffix_len(query_digits, stored_digits)
    if k >= _MIN_MATCH_DIGITS and (k == len(query_digits) or k == len(stored_digits)):
        return k
    return 0


class ContactMatcher:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def resolve(self, raw_number: str, *, region: str = "DE") -> CallerMatch:
        parts = normalize_number(raw_number, region=region)
        if parts.e164 is None:
            return CallerMatch(e164=None, extension=parts.extension)

        cached = _cache.get(parts.e164)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]

        result = await self._match(parts.e164)
        _cache[parts.e164] = (time.monotonic() + _CACHE_TTL, result)
        return result

    async def _match(self, e164: str) -> CallerMatch:
        rows = (
            await self._s.execute(
                select(
                    ContactNumber.e164,
                    ContactNumber.contact_id,
                    Contact.name,
                    ContactPriority.priority,
                )
                .join(Contact, Contact.id == ContactNumber.contact_id)
                .join(
                    ContactPriority,
                    ContactPriority.contact_id == ContactNumber.contact_id,
                    isouter=True,
                )
                .where(Contact.deleted_at.is_(None))
            )
        ).all()

        qd = e164.lstrip("+")
        best_score = 0
        best: list[tuple[str, uuid.UUID, str, str | None]] = []
        for stored_e164, contact_id, name, priority in rows:
            score = _score(qd, stored_e164.lstrip("+"))
            if score == 0:
                continue
            if score > best_score:
                best_score, best = score, [(stored_e164, contact_id, name, priority)]
            elif score == best_score:
                best.append((stored_e164, contact_id, name, priority))

        if not best:
            return CallerMatch(e164=e164)

        contact_ids = {row[1] for row in best}
        if len(contact_ids) > 1:
            return CallerMatch(e164=e164, ambiguous=True)

        stored_e164, contact_id, name, priority = best[0]
        return CallerMatch(
            e164=e164,
            contact_id=contact_id,
            name=name,
            priority=priority,
            matched_on=stored_e164,
        )
