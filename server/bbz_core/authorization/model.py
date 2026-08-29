"""Value objects for authorization decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Grant:
    """One (permission, scope) a user holds via some role.

    ``condition`` is an optional structured Rule-DSL expression (ADR-0010),
    evaluated by the scope resolver (E02-07); it is never executable code.
    """

    permission_key: str
    scope: str
    condition: Mapping[str, Any] | None = field(default=None, compare=False)


class EffectivePermissions:
    """The union of a user's grants across all roles (direct + via groups).

    Grants are **additive** — there is no negative/deny grant in v1
    (MASTER_PROMPT §12). Scope narrowing is applied by the scope resolver
    (E02-07); this object just records which scopes each key was granted in.
    """

    def __init__(self, grants: Iterable[Grant]) -> None:
        self._grants: dict[str, tuple[Grant, ...]] = {}
        acc: dict[str, list[Grant]] = {}
        for g in grants:
            acc.setdefault(g.permission_key, []).append(g)
        self._grants = {k: tuple(v) for k, v in acc.items()}

    def has(self, permission_key: str) -> bool:
        return permission_key in self._grants

    def scopes_for(self, permission_key: str) -> frozenset[str]:
        return frozenset(g.scope for g in self._grants.get(permission_key, ()))

    def grants_for(self, permission_key: str) -> tuple[Grant, ...]:
        return self._grants.get(permission_key, ())

    def keys(self) -> frozenset[str]:
        return frozenset(self._grants)

    def __len__(self) -> int:
        return len(self._grants)
