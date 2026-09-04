"""Seed the database for the Playwright end-to-end suite (roadmap E07-16 / #123).

Idempotent — safe to re-run against a fresh schema. Creates:

* the RBAC catalog + built-in roles (``seed_rbac``)
* ``admin`` — the ``administrator`` role (every human permission)
* ``kollege`` — an operator with the event + workflow permissions. It never logs
  in during the E2E, so its effective presence is ``offline`` and ``admin`` may
  take an event over from it.
* ``neuling`` — an operator flagged ``must_change`` for the forced-password
  -change flow (E07-02 / #97)
* a published 1-step workflow template ``e2e-bma``
* ``BMA Halle 7 — E2E-Lebenszyklus`` — a fresh (``new``) critical event **with**
  that workflow, for the accept -> acknowledge -> open -> complete-step ->
  archive -> archive-detail -> reactivate walk
* ``BMA Halle 3 — E2E-Übernahme`` — a critical event assigned to ``kollege``, for
  the assign / take-over step
* ``BMA Stellwerk — E2E-Archiv`` — an already archived event, for the standalone
  archive / post-processing / reactivation spec

    python server/scripts/seed_e2e.py

Credentials: admin / kollege, password ``Wolke7-Bahnhof!x`` (override ``E2E_PASS``).
"""

from __future__ import annotations

import asyncio
import os
import uuid

PASSWORD = os.environ.get("E2E_PASS", "Wolke7-Bahnhof!x")

_OPERATOR_PERMS = (
    "events.view",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.assign",
    "events.takeover",
    "events.archive",
    "events.reactivate",
    "events.postprocess",
    "events.export",
    "workflows.view",
    "workflows.execute",
)

_GRAPH: dict[str, object] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event", "label": "BMA-Alarm"},
        {"key": "verify", "type": "function", "kind": "manual", "label": "Vor Ort prüfen"},
        {"key": "e1", "type": "event", "label": "Abgeschlossen"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "verify"},
        {"key": "b", "from": "verify", "to": "e1"},
    ],
}

_LIFECYCLE_TITLE = "BMA Halle 7 — E2E-Lebenszyklus"
_TAKEOVER_TITLE = "BMA Halle 3 — E2E-Übernahme"
_ARCHIVED_TITLE = "BMA Stellwerk — E2E-Archiv"


async def _seed() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from bbz_core.auth.hashing import hash_password
    from bbz_core.authorization.seed import seed_rbac
    from bbz_core.domain.events.aggregate import EventAggregate
    from bbz_core.domain.events.state import EventPriority, EventStatus
    from bbz_core.infra.db import get_sessionmaker
    from bbz_core.infra.models.events import Event
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole
    from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
    from bbz_core.infra.repositories.events import EventRepository
    from bbz_core.infra.repositories.workflow_engine import WorkflowEngineService

    async def user_id(
        s: AsyncSession, username: str, display: str, role_key: str, *, must_change: bool = False
    ) -> uuid.UUID:
        found = (
            await s.execute(select(AuthIdentity).where(AuthIdentity.subject == username))
        ).scalar_one_or_none()
        if found is not None:
            return found.user_id
        u = User(display_name=display, status="active")
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="local", subject=username))
        await s.flush()
        ident = (
            await s.execute(
                select(AuthIdentity).where(
                    AuthIdentity.user_id == u.id, AuthIdentity.provider == "local"
                )
            )
        ).scalar_one()
        s.add(
            LocalCredential(
                auth_identity_id=ident.id,
                password_hash=hash_password(PASSWORD),
                must_change=must_change,
            )
        )
        role_id = (await s.execute(select(Role.id).where(Role.key == role_key))).scalar_one()
        s.add(UserRole(user_id=u.id, role_id=role_id))
        return u.id

    async def make_event(s: AsyncSession, actor: uuid.UUID, title: str) -> uuid.UUID:
        async with s.begin():
            found = await s.scalar(select(Event.id).where(Event.title == title))
            if found is not None:
                return found
            eid = uuid.uuid4()
            agg = EventAggregate.create(
                event_id=eid,
                title=title,
                priority=EventPriority.CRITICAL,
                actor_id=actor,
                description="Brandmeldeanlage — E2E",
                source="bma",
            )
            await EventRepository(s).add(agg, actor_id=actor)
        return eid

    async def drive(s: AsyncSession, eid: uuid.UUID, actor: uuid.UUID, *steps: str) -> None:
        """Walk a fresh event through domain transitions, one committed step at a
        time (mirrors the API). A no-op once the event has left ``new``."""
        async with s.begin():
            if (await EventRepository(s).require(eid)).status is not EventStatus.NEW:
                return
        for step in steps:
            async with s.begin():
                agg = await EventRepository(s).require(eid)
                getattr(agg, step)(actor)
                await EventRepository(s).save(agg, actor_id=actor, expected_version=agg.version)

    async def assign(s: AsyncSession, eid: uuid.UUID, to: uuid.UUID, actor: uuid.UUID) -> None:
        async with s.begin():
            agg = await EventRepository(s).require(eid)
            if agg.assignee_id == to:
                return
            agg.assign(to_user_id=to, actor_id=actor)
            await EventRepository(s).save(agg, actor_id=actor, expected_version=agg.version)

    sm = get_sessionmaker()
    async with sm() as s:
        await seed_rbac(s)

        async with s.begin():
            if await s.scalar(select(Role.id).where(Role.key == "e2e_operator")) is None:
                role = Role(key="e2e_operator", name="E2E Operator")
                s.add(role)
                await s.flush()
                for key in _OPERATOR_PERMS:
                    pid = await s.scalar(select(Permission.id).where(Permission.key == key))
                    s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))

        async with s.begin():
            admin_id = await user_id(s, "admin", "E2E Administrator", "administrator")
            kollege_id = await user_id(s, "kollege", "E2E Kollege", "e2e_operator")
            # #97 — an operator who must set a new password on first login
            await user_id(s, "neuling", "E2E Neuling", "e2e_operator", must_change=True)

        async with s.begin():
            has_tpl = await s.scalar(
                select(WorkflowTemplate.id).where(WorkflowTemplate.key == "e2e-bma")
            )
            if has_tpl is None:
                tpl = WorkflowTemplate(key="e2e-bma", name="E2E BMA-Ablauf")
                s.add(tpl)
                await s.flush()
                s.add(
                    WorkflowTemplateVersion(
                        template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
                    )
                )

        lifecycle_id = await make_event(s, admin_id, _LIFECYCLE_TITLE)
        # idempotent — returns the already-running instance on a re-run
        await WorkflowEngineService(s).start_for_event(lifecycle_id, "e2e-bma", actor_id=admin_id)

        takeover_id = await make_event(s, admin_id, _TAKEOVER_TITLE)
        await assign(s, takeover_id, kollege_id, admin_id)

        archived_id = await make_event(s, admin_id, _ARCHIVED_TITLE)
        await drive(s, archived_id, admin_id, "accept", "acknowledge", "open", "archive")

    print("seed_e2e: ready — admin / kollege / neuling, workflow e2e-bma, 3 events")


if __name__ == "__main__":
    asyncio.run(_seed())
