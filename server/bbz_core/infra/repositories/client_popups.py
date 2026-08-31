"""Client-popup delivery (roadmap E15-14, backend slice).

A trigger ``show_client_popup`` action (E15-06) writes a ``client_popup_events``
row bound to one ``workplace_id`` and appends a ``CLIENT_POPUP_RAISED`` domain
event, so a connected client catches it on the event stream (E03-13). This
service is the client's fetch / acknowledge surface:

* :meth:`pending_for` — the live popups for one workplace (not expired, not
  dismissed);
* :meth:`mark_delivered` — the client confirms it showed the popup — idempotent,
  audited ``CLIENT_POPUP_DELIVERED``;
* :meth:`dismiss` — the operator confirmed / dismissed it.

The popup UI, keyboard handling and the door-open action are Epic 07 / Epic 17.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.client_popup_events import ClientPopupEvent


class ClientPopupError(Exception):
    pass


class PopupNotFoundError(ClientPopupError):
    pass


class PopupWorkplaceMismatchError(ClientPopupError):
    """The popup is bound to a different workplace than the caller claims."""


class ClientPopupService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def pending_for(self, workplace_id: uuid.UUID) -> list[ClientPopupEvent]:
        now = _dt.datetime.now(_dt.UTC)
        stmt = (
            select(ClientPopupEvent)
            .where(
                ClientPopupEvent.workplace_id == workplace_id,
                ClientPopupEvent.dismissed_at.is_(None),
                ClientPopupEvent.expires_at > now,
            )
            .order_by(ClientPopupEvent.created_at.asc())
            .execution_options(populate_existing=True)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def mark_delivered(
        self, popup_id: uuid.UUID, *, workplace_id: uuid.UUID | None, actor_id: uuid.UUID | None
    ) -> ClientPopupEvent:
        row = await self._require(popup_id, workplace_id)
        first_delivery = row.delivered_at is None
        if first_delivery:
            row.delivered_at = _dt.datetime.now(_dt.UTC)
            await AuditService(self._s).write(
                AuditAction.CLIENT_POPUP_DELIVERED,
                actor_user_id=actor_id,
                target_type="client_popup_event",
                target_id=str(popup_id),
                after={"workplace_id": str(row.workplace_id), "kind": row.kind},
            )
        await self._s.commit()
        return row

    async def dismiss(
        self, popup_id: uuid.UUID, *, workplace_id: uuid.UUID | None, actor_id: uuid.UUID | None
    ) -> ClientPopupEvent:
        row = await self._require(popup_id, workplace_id)
        if row.dismissed_at is None:
            row.dismissed_at = _dt.datetime.now(_dt.UTC)
        await self._s.commit()
        return row

    async def _require(
        self, popup_id: uuid.UUID, workplace_id: uuid.UUID | None
    ) -> ClientPopupEvent:
        row = await self._s.get(ClientPopupEvent, popup_id)
        if row is None:
            raise PopupNotFoundError(str(popup_id))
        if workplace_id is not None and row.workplace_id != workplace_id:
            raise PopupWorkplaceMismatchError(str(popup_id))
        return row
