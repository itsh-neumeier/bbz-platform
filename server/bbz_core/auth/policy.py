"""Password policy: minimum length, character-class variety, obvious-guess block.

Configured via ``BBZ_PASSWORD_*`` settings. ``validate`` raises
:class:`PasswordPolicyError` listing *all* failed rules (never partial).
"""

from __future__ import annotations

import string
from dataclasses import dataclass

from bbz_core.settings import get_settings

# Small embedded block-list of the most obvious guesses. Not a substitute for
# length/variety rules; deployments needing HIBP-style checks add that later.
_COMMON = frozenset(
    {
        "password",
        "passwort",
        "12345678",
        "123456789",
        "1234567890",
        "qwertzuiop",
        "qwertyuiop",
        "letmein",
        "changeme",
        "admin123",
        "welcome1",
        "bahnhof1",
        "leitstelle",
    }
)


class PasswordPolicyError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def _char_classes(pw: str) -> int:
    lower = any(c.islower() for c in pw)
    upper = any(c.isupper() for c in pw)
    digit = any(c.isdigit() for c in pw)
    symbol = any(c in string.punctuation or not c.isalnum() for c in pw)
    return sum((lower, upper, digit, symbol))


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int
    min_char_classes: int

    @classmethod
    def from_settings(cls) -> PasswordPolicy:
        s = get_settings()
        return cls(
            min_length=s.password_min_length,
            min_char_classes=s.password_min_char_classes,
        )

    def validate(self, password: str, *, username: str | None = None) -> None:
        reasons: list[str] = []
        if len(password) < self.min_length:
            reasons.append(f"must be at least {self.min_length} characters")
        classes = _char_classes(password)
        if classes < self.min_char_classes:
            reasons.append(f"must mix at least {self.min_char_classes} of lower/upper/digit/symbol")
        if password.lower() in _COMMON:
            reasons.append("is too common")
        if username and len(username) >= 3 and username.lower() in password.lower():
            reasons.append("must not contain the username")
        if reasons:
            raise PasswordPolicyError(reasons)
