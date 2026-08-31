"""Resolve a ringing telephony signal to a configured technical endpoint (E17-03).

Matches by ``calling`` / ``called`` number pattern or CTI route point. Exact
string match for now — the patterns are stored verbatim; regex / prefix matching
is a later refinement. Deterministic: the lowest-id match wins on a tie.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber


async def match_technical_endpoint(
    session: AsyncSession,
    *,
    calling: str | None = None,
    called: str | None = None,
    cti_route_point: str | None = None,
    types: Iterable[str] | None = None,
) -> uuid.UUID | None:
    """The id of the first enabled technical endpoint whose number config matches
    any of ``calling`` / ``called`` / ``cti_route_point``, or ``None``.

    ``types`` restricts to those endpoint types (e.g. ``{"door_station"}``).
    """
    predicates = []
    if called:
        predicates.append(TechnicalEndpointNumber.called_pattern == called)
    if calling:
        predicates.append(TechnicalEndpointNumber.calling_pattern == calling)
    if cti_route_point:
        predicates.append(TechnicalEndpointNumber.cti_route_point == cti_route_point)
    if not predicates:
        return None

    stmt = (
        select(TechnicalEndpoint.id)
        .join(TechnicalEndpointNumber, TechnicalEndpointNumber.endpoint_id == TechnicalEndpoint.id)
        .where(TechnicalEndpoint.enabled.is_(True), or_(*predicates))
        .order_by(TechnicalEndpoint.id)
        .limit(1)
    )
    type_list = list(types or [])
    if type_list:
        stmt = stmt.where(TechnicalEndpoint.type.in_(type_list))
    return (await session.execute(stmt)).scalar_one_or_none()
