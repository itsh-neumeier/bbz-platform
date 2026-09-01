"""Scope resolution: does a granted (permission, scope) cover *this* action?

MASTER_PROMPT §12. A grant with scope ``bbz`` means "within the acting user's
own BBZ"; ``own_events`` means "objects this user owns"; and so on. The
:class:`ScopeContext` carries both the acting user's placement and the target
object's placement — a mismatch, or a missing value on either side, denies.
Never the other way round.

``condition`` (Rule-DSL, ADR-0010) is evaluated against the ADR-0027 RBAC
context (clock + the grant's scope) only when ``BBZ_RBAC_CONDITIONS_ENABLED`` is
true — turning it on is a deliberate operator choice. With the flag off, or on a
parse / evaluation failure, a conditional grant is **deny**. A condition can
only narrow a grant, never widen it.
"""

from __future__ import annotations

import datetime as _dt
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


def condition_allows(grant: Grant, *, now: _dt.datetime | None = None) -> bool:
    """Evaluate ``grant.condition`` against the ADR-0027 RBAC context. Used by
    both the scope-agnostic and the scope-aware permission check."""
    if grant.condition is None:
        return True
    if not get_settings().rbac_conditions_enabled:
        return False  # conditional grants stay deny unless opted in
    from bbz_rule_dsl import Context, evaluate, parse

    n = now or _dt.datetime.now(_dt.UTC)
    context = Context(
        {
            "now.hour": n.hour,
            "now.weekday": n.weekday(),
            "now.iso": n.isoformat(timespec="seconds"),
            "scope": grant.scope,
        }
    )
    try:
        return bool(evaluate(parse(dict(grant.condition)), context))
    except Exception:  # any parse/eval failure is a deny, never an allow
        return False


def grant_resolves(grant: Grant, ctx: ScopeContext) -> bool:
    return scope_covers(grant.scope, ctx) and condition_allows(grant)
