"""User presence store (E02-11).

The *stored* state is what the user last chose. The *effective* state is
``offline`` whenever the user has no live session — this gives auto-offline on
logout / session timeout without a background job (MASTER_PROMPT §13.4).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.identity import PresenceState, User, UserPresence
from bbz_core.infra.models.session import Session


@dataclass(frozen=True)
class PresenceView:
    user_id: uuid.UUID
    display_name: str
    state: str  # effective (offline if no live session)
    stored_state: str
    changed_at: _dt.datetime | None


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class PresenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def set_state(
        self, user_id: uuid.UUID, state: PresenceState, *, changed_by: uuid.UUID | None
    ) -> None:
        stmt = insert(UserPresence).values(
            user_id=user_id, state=state.value, changed_at=_now(), changed_by=changed_by
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[UserPresence.user_id],
            set_={"state": state.value, "changed_at": _now(), "changed_by": changed_by},
        )
        await self._s.execute(stmt)
        await self._s.commit()

    async def set_offline(self, user_id: uuid.UUID) -> None:
        await self.set_state(user_id, PresenceState.OFFLINE, changed_by=user_id)

    def _query(self) -> Select[Any]:
        live = exists().where(
            Session.user_id == User.id,
            Session.revoked_at.is_(None),
            Session.expires_at > _now(),
        )
        return select(
            User.id,
            User.display_name,
            UserPresence.state,
            UserPresence.changed_at,
            live,
        ).outerjoin(UserPresence, UserPresence.user_id == User.id)

    @staticmethod
    def _view(row: Any) -> PresenceView:
        uid, name, state, changed_at, live = row
        stored = state or PresenceState.OFFLINE.value
        effective = stored if live else PresenceState.OFFLINE.value
        return PresenceView(uid, name, effective, stored, changed_at)

    async def get(self, user_id: uuid.UUID) -> PresenceView | None:
        row = (await self._s.execute(self._query().where(User.id == user_id))).first()
        return self._view(row) if row is not None else None

    async def list_all(self) -> list[PresenceView]:
        rows = await self._s.execute(self._query().order_by(User.display_name))
        return [self._view(r) for r in rows.all()]
