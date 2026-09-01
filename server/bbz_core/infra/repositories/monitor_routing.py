"""Monitor / KVM routing service (roadmap E19-04, MASTER_PROMPT §9/§17).

Sets routes and resets to the standard layout as **audited, idempotent** commands
that are executed on the active monitor provider (``monitor_mock`` now,
``monitor_weytec`` later — E19-07). Every applied change writes a
``MONITOR_ROUTE_CHANGED`` audit row (a critical action).

Validation — unknown ports and the fixed "lower-left is always BBZ-OS" rule
(E19-03) — is the domain's (:mod:`bbz_core.domain.monitor`); this service persists
the result and drives the provider.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.monitor import (
    OUTPUTS,
    is_fixed_output,
    standard_layout,
    validate_assignment,
)
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.monitor import MonitorInput, MonitorOutput, MonitorRoute
from bbz_core.integrations_host.providers import NoActiveProvider, active_monitor_provider
from bbz_core.logging import get_logger

_log = get_logger(__name__)

_PUT = "PUT /api/v1/monitor/routes"
_RESET = "POST /api/v1/monitor/routes/reset-standard"


class MonitorProviderError(RuntimeError):
    """The active monitor provider rejected or failed to apply a route."""


@dataclass(frozen=True)
class RouteView:
    output_key: str
    input_key: str | None
    is_fixed: bool
    set_at: _dt.datetime | None


@dataclass(frozen=True)
class MonitorState:
    routes: list[RouteView]
    provider_available: bool
    provider_healthy: bool

    def as_body(self) -> dict[str, object]:
        return {
            "routes": [
                {
                    "output_key": r.output_key,
                    "input_key": r.input_key,
                    "is_fixed": r.is_fixed,
                    "set_at": r.set_at.isoformat() if r.set_at else None,
                }
                for r in self.routes
            ],
            "provider_available": self.provider_available,
            "provider_healthy": self.provider_healthy,
        }


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class MonitorRoutingService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- read --------------------------------------------------------

    async def state(self) -> MonitorState:
        await self._s.rollback()
        rows = await self._current_routes()
        routes = [
            RouteView(
                output_key=o.key,
                input_key=rows.get(o.key, (None, None))[0],
                is_fixed=is_fixed_output(o.key),
                set_at=rows.get(o.key, (None, None))[1],
            )
            for o in OUTPUTS
        ]
        available, healthy = await self._provider_health()
        return MonitorState(routes=routes, provider_available=available, provider_healthy=healthy)

    # --- writes ----------------------------------------------------

    async def set_routes(
        self,
        *,
        assignments: dict[str, str],
        command_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> MonitorState:
        for output_key, input_key in assignments.items():
            validate_assignment(output_key, input_key)  # domain: unknown key / fixed rule
        rhash = request_hash({"reset": False, "assignments": assignments})
        async with idempotent(
            self._s, command_id=command_id, endpoint=_PUT, request_hash=rhash, user_id=actor_id
        ) as slot:
            if slot.replay is None:
                await self.apply_assignments(assignments, command_id=command_id, actor_id=actor_id)
                slot.set_result(200, {"ok": True})
            return await self.state()

    async def reset_to_standard(
        self, *, command_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> MonitorState:
        assignments = standard_layout()
        rhash = request_hash({"reset": True, "assignments": assignments})
        async with idempotent(
            self._s, command_id=command_id, endpoint=_RESET, request_hash=rhash, user_id=actor_id
        ) as slot:
            if slot.replay is None:
                await self.apply_assignments(assignments, command_id=command_id, actor_id=actor_id)
                slot.set_result(200, {"ok": True})
            return await self.state()

    # --- apply ---------------------------------------------------

    async def apply_assignments(
        self,
        assignments: dict[str, str],
        *,
        command_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        profile_id: uuid.UUID | None = None,
    ) -> None:
        """Validate, drive the provider for every *changed* output, persist the
        routes and write one ``MONITOR_ROUTE_CHANGED`` per change — all in one
        transaction. Has **no** idempotency guard of its own; the caller wraps it
        in :func:`idempotent`. ``profile_id`` stamps the route rows when a profile
        is being applied (E19-05)."""
        for output_key, input_key in assignments.items():
            validate_assignment(output_key, input_key)

        await self._s.rollback()
        current = {k: v[0] for k, v in (await self._current_routes()).items()}
        changes = {o: i for o, i in assignments.items() if current.get(o) != i}

        if changes:
            provider = await active_monitor_provider()
            for output_key, input_key in changes.items():
                try:
                    await provider.set_route(
                        output_id=output_key,
                        input_id=input_key,
                        command_id=f"{command_id}:{output_key}",
                    )
                except NoActiveProvider:
                    raise
                except Exception as exc:  # the mock raises RuntimeError subclasses
                    raise MonitorProviderError(
                        f"provider rejected {output_key} <- {input_key}: {exc}"
                    ) from exc

        out_ids = {o.key: o.id for o in await self._outputs()}
        in_ids = {i.key: i.id for i in (await self._s.execute(select(MonitorInput))).scalars()}
        now = _now()
        await self._s.rollback()
        async with self._s.begin():
            for output_key, input_key in changes.items():
                await self._s.execute(
                    pg_insert(MonitorRoute)
                    .values(
                        output_id=out_ids[output_key],
                        input_id=in_ids[input_key],
                        set_by=actor_id,
                        set_at=now,
                        profile_id=profile_id,
                    )
                    .on_conflict_do_update(
                        index_elements=["output_id"],
                        set_={
                            "input_id": in_ids[input_key],
                            "set_by": actor_id,
                            "set_at": now,
                            "profile_id": profile_id,
                            "updated_at": now,
                        },
                    )
                )
                await AuditService(self._s).write(
                    AuditAction.MONITOR_ROUTE_CHANGED,
                    actor_user_id=actor_id,
                    target_type="monitor_output",
                    target_id=output_key,
                    before={"input": current.get(output_key)},
                    after={"input": input_key},
                )

    # --- helpers -----------------------------------------------

    async def _outputs(self) -> list[MonitorOutput]:
        return list((await self._s.execute(select(MonitorOutput))).scalars().all())

    async def _current_routes(self) -> dict[str, tuple[str, _dt.datetime | None]]:
        rows = (
            await self._s.execute(
                select(MonitorOutput.key, MonitorInput.key, MonitorRoute.set_at)
                .select_from(MonitorRoute)
                .join(MonitorOutput, MonitorOutput.id == MonitorRoute.output_id)
                .join(MonitorInput, MonitorInput.id == MonitorRoute.input_id)
            )
        ).all()
        return {output_key: (input_key, set_at) for output_key, input_key, set_at in rows}

    async def _provider_health(self) -> tuple[bool, bool]:
        try:
            provider = await active_monitor_provider()
        except NoActiveProvider:
            return False, False
        try:
            report = await provider.health()
        except Exception as exc:  # a flaky provider must not 500 a read
            _log.warning("monitor_provider_health_failed", error=repr(exc))
            return True, False
        return True, report.state == "healthy"
