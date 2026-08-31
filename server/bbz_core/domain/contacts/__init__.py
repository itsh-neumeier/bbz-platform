"""Pure contact-domain helpers (no I/O). Phone-number normalization for the
caller-resolution matcher (roadmap E14-04)."""

from __future__ import annotations

from bbz_core.domain.contacts.phone_numbers import (
    DEFAULT_REGION,
    NumberParts,
    normalize_number,
)

__all__ = ["DEFAULT_REGION", "NumberParts", "normalize_number"]
