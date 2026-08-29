"""Scope resolution: does a granted (permission, scope) cover *this* action?

MASTER_PROMPT §12. A grant with scope ``bbz`` means "within the acting user's
own BBZ"; ``own_events`` means "objects this user owns"; and so on. The
:class:`ScopeContext` carries both the acting user's placement and the target
object's placement — a mismatch, or a missing value on either side, denies.
Never the other way round.

``condition`` (Rule-DSL, ADR-0010) is evaluated only when
``BBZ_RBAC_CONDITIONS_ENABLED`` is true; until the DSL evaluator ships
(E05-01) a conditional grant is treated as **deny**.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from bbz_core.authorization.model import Grant
from bbz_core.authorization.scopes import Scope
from bbz_core.settings import get_settings


@dataclass(frozen=True)
class ScopeContext:
    acting_user_id: uuid.UUID
    # acting user's placement (None until multi-tenancy lands — bbz/region/
    # workplace grants then simply do not resolve, which is the safe default)
    user_region_id: uuid.UUID | None = None
    user_bbz_id: uuid.UUID | None = None
    user_workplace_id: uuid.UUID | None = None
    # target object's placement / ownership
    target_region_id: uuid.UUID | None = None
    target_bbz_id: uuid.UUID | None = None
    target_workplace_id: uuid.UUID | None = None
    target_owner_id: uuid.UUID | None = None
    target_assignee_id: uuid.UUID | None = None


def _both(a: uuid.UUID | None, b: uuid.UUID | None) -> bool:
    return a is not None and b is not None and a == b


def scope_covers(scope: str, ctx: ScopeContext) -> bool:
    match scope:
        case Scope.GLOBAL:
            return True
        case Scope.REGION:
            return _both(ctx.user_region_id, ctx.target_region_id)
        case Scope.BBZ:
            return _both(ctx.user_bbz_id, ctx.target_bbz_id)
        case Scope.WORKPLACE:
            return _both(ctx.user_workplace_id, ctx.target_workplace_id)
        case Scope.OWN_EVENTS:
            return _both(ctx.acting_user_id, ctx.target_owner_id)
        case Scope.ASSIGNED_EVENTS:
            return _both(ctx.acting_user_id, ctx.target_assignee_id)
        case _:
            return False  # unknown scope value -> deny


def _condition_allows(grant: Grant, ctx: ScopeContext) -> bool:
    if grant.condition is None:
        return True
    if not get_settings().rbac_conditions_enabled:
        return False  # safe default until the Rule-DSL evaluator ships (E05-01)
    # Feature flag is on: attempt real evaluation. The RBAC condition context
    # (which ScopeContext fields map to which allowlisted DSL fields) is defined
    # together with the DSL field registry in E05-02; until then any parse/eval
    # error is a deny, never an allow.
    from bbz_rule_dsl import Context, RuleDslError, evaluate, parse

    try:
        return bool(evaluate(parse(dict(grant.condition)), Context()))
    except (NotImplementedError, RuleDslError):
        return False


def grant_resolves(grant: Grant, ctx: ScopeContext) -> bool:
    return scope_covers(grant.scope, ctx) and _condition_allows(grant, ctx)
