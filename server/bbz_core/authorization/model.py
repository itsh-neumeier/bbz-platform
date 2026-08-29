"""Value objects for authorization decisions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Grant:
    """One (permission, scope) a user holds via some role."""

    permission_key: str
    scope: str


class EffectivePermissions:
    """The union of a user's grants across all roles (direct + via groups).

    Grants are **additive** — there is no negative/deny grant in v1
    (MASTER_PROMPT §12). Scope narrowing is applied by the scope resolver
    (E02-07); this object just records which scopes each key was granted in.
    """

    def __init__(self, grants: Iterable[Grant]) -> None:
        by_key: dict[str, set[str]] = {}
        for g in grants:
            by_key.setdefault(g.permission_key, set()).add(g.scope)
        self._by_key: dict[str, frozenset[str]] = {k: frozenset(v) for k, v in by_key.items()}

    def has(self, permission_key: str) -> bool:
        return permission_key in self._by_key

    def scopes_for(self, permission_key: str) -> frozenset[str]:
        return self._by_key.get(permission_key, frozenset())

    def keys(self) -> frozenset[str]:
        return frozenset(self._by_key)

    def __len__(self) -> int:
        return len(self._by_key)
