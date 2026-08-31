"""Technical-endpoint admin repository (roadmap E15-10).

CRUD over :class:`TechnicalEndpoint` + its telephony number patterns. Highly
privileged — an endpoint drives automatic event creation and (for door
stations) automatic door opening, so every mutation writes a
``TECHNICAL_ENDPOINT_*`` audit row in the same transaction and bumps
``active_config_version``.

Each mutating method commits its own transaction (mirrors
:class:`bbz_core.infra.repositories.workflow_lifecycle.WorkflowLifecycleService`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService, changed_fields
from bbz_core.infra.models.technical_endpoints import (
    TechnicalEndpoint,
    TechnicalEndpointNumber,
    TechnicalEndpointType,
)

_PRIORITIES = frozenset({"critical", "high", "medium", "low"})

_MUTABLE_FIELDS = frozenset(
    {
        "name",
        "site",
        "type",
        "provider_id",
        "external_source_ids",
        "default_priority",
        "popup_profile",
        "escalation_profile",
        "workflow_selection_policy",
        "enabled",
        "dtmf_profile_id",
        "popup_text",
        "door_open_timeout_seconds",
    }
)


class TechnicalEndpointError(ValueError):
    pass


class EndpointNotFoundError(TechnicalEndpointError):
    pass


class InvalidEndpointError(TechnicalEndpointError):
    """A field value is not acceptable (bad type / priority / …)."""


@dataclass(frozen=True)
class NumberPattern:
    calling_pattern: str | None = None
    called_pattern: str | None = None
    cti_route_point: str | None = None


@dataclass
class EndpointInput:
    name: str
    type: str
    site: str | None = None
    provider_id: str | None = None
    external_source_ids: list[str] = field(default_factory=list)
    default_priority: str | None = None
    popup_profile: str | None = None
    escalation_profile: str | None = None
    workflow_selection_policy: dict[str, Any] | None = None
    enabled: bool = True
    numbers: list[NumberPattern] = field(default_factory=list)
    #: door-station config (E17-01). ``dtmf_profile_id`` is an id only.
    dtmf_profile_id: uuid.UUID | None = None
    popup_text: str | None = None
    door_open_timeout_seconds: int | None = None


@dataclass(frozen=True)
class EndpointView:
    endpoint: TechnicalEndpoint
    numbers: list[TechnicalEndpointNumber]


class TechnicalEndpointService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # Reads never ``rollback()`` and always ``populate_existing`` — a mutating
    # method commits just before returning a view, which expires the
    # server-generated columns (``updated_at``); a plain identity-map read would
    # then hand the router a half-expired object and blow up on serialisation.

    async def list_all(self) -> list[TechnicalEndpoint]:
        return list(
            (
                await self._s.execute(
                    select(TechnicalEndpoint)
                    .order_by(TechnicalEndpoint.name, TechnicalEndpoint.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

    async def list_views(self) -> list[EndpointView]:
        """Every endpoint with its number patterns — two queries, grouped."""
        endpoints = await self.list_all()
        rows = (
            (
                await self._s.execute(
                    select(TechnicalEndpointNumber)
                    .order_by(TechnicalEndpointNumber.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        by_endpoint: dict[uuid.UUID, list[TechnicalEndpointNumber]] = {}
        for n in rows:
            by_endpoint.setdefault(n.endpoint_id, []).append(n)
        return [EndpointView(e, by_endpoint.get(e.id, [])) for e in endpoints]

    async def get(self, endpoint_id: uuid.UUID) -> EndpointView:
        endpoint = (
            await self._s.execute(
                select(TechnicalEndpoint)
                .where(TechnicalEndpoint.id == endpoint_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if endpoint is None:
            raise EndpointNotFoundError(str(endpoint_id))
        return EndpointView(endpoint, await self._numbers(endpoint_id))

    async def create(self, data: EndpointInput, *, actor_id: uuid.UUID | None) -> EndpointView:
        _validate_type(data.type)
        _validate_priority(data.default_priority)
        await self._s.rollback()
        endpoint = TechnicalEndpoint(
            name=data.name,
            site=data.site,
            type=data.type,
            provider_id=data.provider_id,
            external_source_ids=list(data.external_source_ids),
            default_priority=data.default_priority,
            popup_profile=data.popup_profile,
            escalation_profile=data.escalation_profile,
            workflow_selection_policy=data.workflow_selection_policy,
            enabled=data.enabled,
            dtmf_profile_id=data.dtmf_profile_id,
            popup_text=data.popup_text,
            door_open_timeout_seconds=data.door_open_timeout_seconds,
        )
        self._s.add(endpoint)
        await self._s.flush()
        await self._replace_numbers(endpoint.id, data.numbers)
        await self._audit(
            AuditAction.TECHNICAL_ENDPOINT_CREATED,
            endpoint,
            actor_id,
            after=_snapshot(endpoint, data.numbers),
        )
        await self._s.commit()
        return await self.get(endpoint.id)

    async def update(
        self,
        endpoint_id: uuid.UUID,
        changes: dict[str, Any],
        *,
        numbers: list[NumberPattern] | None,
        actor_id: uuid.UUID | None,
    ) -> EndpointView:
        unknown = set(changes) - _MUTABLE_FIELDS
        if unknown:
            raise InvalidEndpointError(f"cannot change: {', '.join(sorted(unknown))}")
        if "type" in changes:
            _validate_type(changes["type"])
        if "default_priority" in changes:
            _validate_priority(changes["default_priority"])

        await self._s.rollback()
        endpoint = await self._s.get(TechnicalEndpoint, endpoint_id)
        if endpoint is None:
            raise EndpointNotFoundError(str(endpoint_id))

        before = {k: _jsonable(getattr(endpoint, k)) for k in changes}
        for key, value in changes.items():
            setattr(endpoint, key, value)
        after = {k: _jsonable(getattr(endpoint, k)) for k in changes}
        diff = changed_fields(before, after)

        numbers_changed = False
        if numbers is not None:
            old = {_num_tuple(n) for n in await self._numbers(endpoint_id)}
            new = {(n.calling_pattern, n.called_pattern, n.cti_route_point) for n in numbers}
            if old != new:
                await self._replace_numbers(endpoint_id, numbers)
                numbers_changed = True

        if not diff and not numbers_changed:
            await self._s.rollback()
            return await self.get(endpoint_id)

        endpoint.active_config_version = endpoint.active_config_version + 1
        payload: dict[str, Any] = {"changes": diff}
        if numbers_changed:
            payload["numbers"] = [_num_tuple(n) for n in await self._numbers(endpoint_id)]
        await self._audit(AuditAction.TECHNICAL_ENDPOINT_UPDATED, endpoint, actor_id, after=payload)
        await self._s.commit()
        return await self.get(endpoint_id)

    async def delete(self, endpoint_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        endpoint = await self._s.get(TechnicalEndpoint, endpoint_id)
        if endpoint is None:
            raise EndpointNotFoundError(str(endpoint_id))
        name = endpoint.name
        await self._audit(
            AuditAction.TECHNICAL_ENDPOINT_DELETED,
            endpoint,
            actor_id,
            after={"name": name},
        )
        await self._s.execute(delete(TechnicalEndpoint).where(TechnicalEndpoint.id == endpoint_id))
        await self._s.commit()

    # --- internals ----------------------------------------------------------

    async def _numbers(self, endpoint_id: uuid.UUID) -> list[TechnicalEndpointNumber]:
        return list(
            (
                await self._s.execute(
                    select(TechnicalEndpointNumber)
                    .where(TechnicalEndpointNumber.endpoint_id == endpoint_id)
                    .order_by(TechnicalEndpointNumber.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

    async def _replace_numbers(self, endpoint_id: uuid.UUID, numbers: list[NumberPattern]) -> None:
        await self._s.execute(
            delete(TechnicalEndpointNumber).where(
                TechnicalEndpointNumber.endpoint_id == endpoint_id
            )
        )
        for n in numbers:
            self._s.add(
                TechnicalEndpointNumber(
                    endpoint_id=endpoint_id,
                    calling_pattern=n.calling_pattern,
                    called_pattern=n.called_pattern,
                    cti_route_point=n.cti_route_point,
                )
            )
        await self._s.flush()

    async def _audit(
        self,
        action: AuditAction,
        endpoint: TechnicalEndpoint,
        actor_id: uuid.UUID | None,
        *,
        after: dict[str, Any],
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="technical_endpoint",
            target_id=str(endpoint.id),
            after=after,
        )


def _validate_type(value: Any) -> None:
    try:
        TechnicalEndpointType(str(value))
    except ValueError as exc:
        raise InvalidEndpointError(f"unknown endpoint type: {value!r}") from exc


def _validate_priority(value: Any) -> None:
    if value is not None and value not in _PRIORITIES:
        raise InvalidEndpointError(f"invalid default_priority: {value!r}")


def _num_tuple(n: TechnicalEndpointNumber) -> tuple[str | None, str | None, str | None]:
    return (n.calling_pattern, n.called_pattern, n.cti_route_point)


def _snapshot(endpoint: TechnicalEndpoint, numbers: list[NumberPattern]) -> dict[str, Any]:
    return {
        "name": endpoint.name,
        "type": endpoint.type,
        "site": endpoint.site,
        "provider_id": endpoint.provider_id,
        "enabled": endpoint.enabled,
        "number_count": len(numbers),
    }


def _jsonable(value: object) -> object:
    return str(value) if isinstance(value, uuid.UUID) else value
