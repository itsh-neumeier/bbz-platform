"""Monitor layout profiles (roadmap E19-05, MASTER_PROMPT §9).

A profile is a named, re-applicable ``{output_key: input_key}`` layout with a
scope:

* ``user``      — private to its ``owner_user_id``;
* ``workplace`` — shared for a ``workplace_id`` (a plain UUID — no ``workplaces``
  entity yet).

CRUD needs ``monitor.manage_profiles``; applying one is a routing action
(``monitor.route``) and goes through :class:`MonitorRoutingService` so the fixed
"lower-left is always BBZ-OS" rule and the ``MONITOR_ROUTE_CHANGED`` audit apply.
Applying also writes one ``MONITOR_PROFILE_APPLIED`` row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.monitor import MonitorDomainError, validate_layout
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.monitor import MonitorProfile
from bbz_core.infra.repositories.monitor_routing import MonitorRoutingService, MonitorState

_APPLY = "POST /api/v1/monitor/profiles/{id}/apply"


class MonitorProfileNotFoundError(LookupError):
    """No visible profile with that id for this actor."""


class MonitorProfileNameConflict(ValueError):
    """A profile with that name already exists in the same scope."""


class MonitorProfileScopeError(MonitorDomainError):
    """A ``workplace`` profile without a ``workplace_id`` (or vice versa)."""


@dataclass(frozen=True)
class ProfileView:
    id: uuid.UUID
    name: str
    scope: str
    workplace_id: uuid.UUID | None
    layout: dict[str, str]


def _view(p: MonitorProfile) -> ProfileView:
    return ProfileView(
        id=p.id, name=p.name, scope=p.scope, workplace_id=p.workplace_id, layout=dict(p.layout)
    )


class MonitorProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_visible(
        self, *, user_id: uuid.UUID, workplace_id: uuid.UUID | None
    ) -> list[ProfileView]:
        await self._s.rollback()
        conds = [(MonitorProfile.scope == "user") & (MonitorProfile.owner_user_id == user_id)]
        if workplace_id is not None:
            conds.append(
                (MonitorProfile.scope == "workplace")
                & (MonitorProfile.workplace_id == workplace_id)
            )
        rows = (
            await self._s.execute(
                select(MonitorProfile).where(or_(*conds)).order_by(MonitorProfile.name)
            )
        ).scalars()
        return [_view(p) for p in rows]

    async def create(
        self,
        *,
        name: str,
        scope: str,
        layout: dict[str, str],
        user_id: uuid.UUID,
        workplace_id: uuid.UUID | None,
    ) -> ProfileView:
        validate_layout(layout)  # domain: every output, known inputs, fixed rule
        owner: uuid.UUID | None
        if scope == "user":
            owner, wp = user_id, None
        elif scope == "workplace":
            if workplace_id is None:
                raise MonitorProfileScopeError("a workplace profile needs a workplace_id")
            owner, wp = None, workplace_id
        else:
            raise MonitorProfileScopeError(f"unknown scope {scope!r}")

        profile = MonitorProfile(
            name=name.strip(), scope=scope, owner_user_id=owner, workplace_id=wp, layout=layout
        )
        await self._s.rollback()
        try:
            async with self._s.begin():
                if await self._name_taken(name.strip(), scope, owner, wp):
                    raise MonitorProfileNameConflict(name)
                self._s.add(profile)
        except IntegrityError as exc:
            raise MonitorProfileNameConflict(name) from exc
        return _view(profile)

    async def update(
        self,
        *,
        profile_id: uuid.UUID,
        user_id: uuid.UUID,
        workplace_id: uuid.UUID | None,
        name: str | None = None,
        layout: dict[str, str] | None = None,
    ) -> ProfileView:
        if layout is not None:
            validate_layout(layout)
        await self._s.rollback()
        async with self._s.begin():
            profile = await self._require_visible(profile_id, user_id, workplace_id)
            if name is not None:
                profile.name = name.strip()
            if layout is not None:
                profile.layout = layout
        return _view(profile)

    async def delete(
        self, *, profile_id: uuid.UUID, user_id: uuid.UUID, workplace_id: uuid.UUID | None
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            profile = await self._require_visible(profile_id, user_id, workplace_id)
            await self._s.delete(profile)

    async def apply(
        self,
        *,
        profile_id: uuid.UUID,
        command_id: uuid.UUID,
        user_id: uuid.UUID,
        workplace_id: uuid.UUID | None,
    ) -> MonitorState:
        await self._s.rollback()
        profile = await self._require_visible(profile_id, user_id, workplace_id)
        layout, name, scope = dict(profile.layout), profile.name, profile.scope
        rhash = request_hash({"profile": str(profile_id), "layout": layout})
        routing = MonitorRoutingService(self._s)
        async with idempotent(
            self._s, command_id=command_id, endpoint=_APPLY, request_hash=rhash, user_id=user_id
        ) as slot:
            if slot.replay is None:
                await routing.apply_assignments(
                    layout, command_id=command_id, actor_id=user_id, profile_id=profile_id
                )
                await self._s.rollback()
                async with self._s.begin():
                    await AuditService(self._s).write(
                        AuditAction.MONITOR_PROFILE_APPLIED,
                        actor_user_id=user_id,
                        target_type="monitor_profile",
                        target_id=str(profile_id),
                        after={"name": name, "scope": scope},
                    )
                slot.set_result(200, {"ok": True})
            return await routing.state()

    # --- helpers -------------------------------------------------

    async def _name_taken(
        self, name: str, scope: str, owner: uuid.UUID | None, wp: uuid.UUID | None
    ) -> bool:
        stmt = select(MonitorProfile.id).where(
            MonitorProfile.scope == scope, MonitorProfile.name == name
        )
        stmt = stmt.where(
            MonitorProfile.owner_user_id == owner
            if scope == "user"
            else MonitorProfile.workplace_id == wp
        )
        return (await self._s.execute(stmt)).first() is not None

    async def _require_visible(
        self, profile_id: uuid.UUID, user_id: uuid.UUID, workplace_id: uuid.UUID | None
    ) -> MonitorProfile:
        profile = await self._s.get(MonitorProfile, profile_id)
        visible = profile is not None and (
            (profile.scope == "user" and profile.owner_user_id == user_id)
            or (profile.scope == "workplace" and profile.workplace_id == workplace_id)
        )
        if not visible:
            raise MonitorProfileNotFoundError(str(profile_id))
        assert profile is not None
        return profile
