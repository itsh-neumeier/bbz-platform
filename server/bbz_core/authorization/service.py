"""The permission-check service: 'may user X do permission P?'.

Scope-agnostic in E02-06 — ``authorize`` is True if the user holds the
permission under *any* scope. E02-07 adds a scope-aware overload that takes a
:class:`ScopeContext`. Instances are meant to be **request-scoped**: the
per-user cache then behaves as a request-local memoisation (HA-safe, no cross
-request staleness).
"""

from __future__ import annotations

import uuid
from typing import Protocol

from bbz_core.authorization.keys import assert_known
from bbz_core.authorization.model import EffectivePermissions, Grant


class GrantStore(Protocol):
    async def grants_for_user(self, user_id: uuid.UUID) -> list[Grant]: ...


class PermissionService:
    def __init__(self, store: GrantStore) -> None:
        self._store = store
        self._cache: dict[uuid.UUID, EffectivePermissions] = {}

    async def effective(self, user_id: uuid.UUID) -> EffectivePermissions:
        cached = self._cache.get(user_id)
        if cached is None:
            cached = EffectivePermissions(await self._store.grants_for_user(user_id))
            self._cache[user_id] = cached
        return cached

    async def authorize(self, user_id: uuid.UUID, permission_key: str) -> bool:
        assert_known(permission_key)  # unknown key -> PermissionKeyError, never a silent allow
        return (await self.effective(user_id)).has(permission_key)
