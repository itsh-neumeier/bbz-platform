"""Scope resolution matrix + conditional-grant safe default."""

from __future__ import annotations

import uuid

import pytest

from bbz_core.authorization import Grant, PermissionService, Scope, ScopeContext, scope_covers
from bbz_core.authorization.resolver import grant_resolves

USER = uuid.uuid4()
BBZ_A = uuid.uuid4()
BBZ_B = uuid.uuid4()
OWNER = uuid.uuid4()


def ctx(**over: object) -> ScopeContext:
    base: dict[str, object] = {"acting_user_id": USER}
    base.update(over)
    return ScopeContext(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("scope", "context", "expected"),
    [
        (Scope.GLOBAL, ctx(), True),
        (Scope.BBZ, ctx(user_bbz_id=BBZ_A, target_bbz_id=BBZ_A), True),
        (Scope.BBZ, ctx(user_bbz_id=BBZ_A, target_bbz_id=BBZ_B), False),
        (Scope.BBZ, ctx(target_bbz_id=BBZ_A), False),  # user placement unknown -> deny
        (Scope.BBZ, ctx(user_bbz_id=BBZ_A), False),  # target placement unknown -> deny
        (Scope.WORKPLACE, ctx(user_workplace_id=BBZ_A, target_workplace_id=BBZ_A), True),
        (Scope.OWN_EVENTS, ctx(target_owner_id=USER), True),
        (Scope.OWN_EVENTS, ctx(target_owner_id=OWNER), False),
        (Scope.ASSIGNED_EVENTS, ctx(target_assignee_id=USER), True),
        (Scope.ASSIGNED_EVENTS, ctx(), False),
    ],
)
def test_scope_covers_matrix(scope: Scope, context: ScopeContext, expected: bool) -> None:
    assert scope_covers(scope.value, context) is expected


def test_unknown_scope_value_denies() -> None:
    assert scope_covers("universe", ctx()) is False


def test_conditional_grant_denies_until_dsl_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    g = Grant("events.takeover", Scope.GLOBAL.value, condition={"op": "eq", "args": []})
    # global scope covers, but the condition cannot be evaluated -> deny
    assert grant_resolves(g, ctx()) is False


async def test_authorize_scoped_picks_the_resolving_grant() -> None:
    class Store:
        async def grants_for_user(self, user_id: uuid.UUID) -> list[Grant]:
            return [
                Grant("events.takeover", Scope.BBZ.value),  # will not resolve (no placement)
                Grant("events.takeover", Scope.OWN_EVENTS.value),  # resolves for own object
            ]

    svc = PermissionService(Store())
    assert await svc.authorize_scoped(USER, "events.takeover", ctx(target_owner_id=USER)) is True
    assert await svc.authorize_scoped(USER, "events.takeover", ctx(target_owner_id=OWNER)) is False
    # scope-agnostic check still passes (the user *has* the permission somewhere)
    assert await svc.authorize(USER, "events.takeover") is True
