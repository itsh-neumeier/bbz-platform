"""Rate-limit FastAPI dependencies (roadmap E23-04, MASTER_PROMPT §22).

Named rules (thresholds from settings) applied to the abuse-prone endpoints —
login, MFA verify, password reset, inbound integration webhooks. The counter is
cluster-wide (:class:`bbz_core.infra.rate_limit.RateLimiter` → ``rate_limit_hits``).
Over the limit ⇒ ``429`` with ``Retry-After``; the auth-path rules also audit
``RATE_LIMIT_TRIGGERED`` (rule + identifier, no payload).

WAF / network DDoS is out of scope (that is the edge's job).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from bbz_core.api.deps import AuthContext, current_auth
from bbz_core.api.errors import RateLimitedError
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.db import session_scope
from bbz_core.infra.rate_limit import RateLimiter, RateLimitRule
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)

#: rules whose breach is worth an audit row (security-relevant paths)
_AUDITED = frozenset({"login", "mfa", "password_reset"})


def _rule(name: str) -> RateLimitRule | None:
    raw = getattr(get_settings(), f"rate_limit_{name}", "")
    try:
        limit_s, window_s = raw.split("/", 1)
        limit, window = int(limit_s), int(window_s)
    except (ValueError, AttributeError):
        return None
    if limit <= 0 or window <= 0:
        return None
    return RateLimitRule(name=name, limit=limit, window_seconds=window)


def client_ip(request: Request) -> str:
    """The caller's IP. Trusts the reverse proxy's ``X-Forwarded-For`` (Caddy
    sets it, E06-12); falls back to the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _enforce(rule: RateLimitRule, identifier: str) -> None:
    try:
        async with session_scope() as session:
            result = await RateLimiter(session).hit(rule, identifier)
    except (SQLAlchemyError, OSError) as exc:
        # fail OPEN — a limiter that can't reach its store must not 500 the request
        _log.warning("rate_limit_store_unavailable", rule=rule.name, error=str(exc))
        return
    if result.allowed:
        return
    if rule.name in _AUDITED:
        async with session_scope() as session, session.begin():
            await AuditService(session).write(
                AuditAction.RATE_LIMIT_TRIGGERED,
                target_type="rate_limit",
                target_id=f"{rule.name}:{identifier}"[:200],
                after={"rule": rule.name, "limit": rule.limit, "count": result.count},
            )
    raise RateLimitedError(
        f"too many requests for {rule.name}",
        details={"retry_after": result.retry_after},
        headers={"Retry-After": str(result.retry_after)},
    )


def rate_limit_by_ip(name: str) -> Callable[[Request], Awaitable[None]]:
    async def _dep(request: Request) -> None:
        rule = _rule(name)
        if rule is not None:
            await _enforce(rule, client_ip(request))

    return _dep


def rate_limit_by_user(name: str) -> Callable[..., Awaitable[None]]:
    from fastapi import Depends

    async def _dep(request: Request, ctx: AuthContext = Depends(current_auth)) -> None:
        rule = _rule(name)
        if rule is not None:
            await _enforce(rule, f"user:{ctx.user_id}")

    return _dep
