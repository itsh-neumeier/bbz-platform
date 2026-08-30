"""Phone-book persistence: contacts + their numbers (roadmap E14-02).

CRUD and search over ``contacts`` / ``contact_numbers``. Deletion is **soft**
(``contacts.deleted_at``) — a deleted contact drops out of every read here.
Search matches ``name`` / ``org`` (substring, case-insensitive, ``pg_trgm``
GIN-backed) and ``contact_numbers.e164`` (substring); results are alphabetical
by name and keyset-paginated on ``(lower(name), id)`` so a new contact never
shifts a page.

Priority (``contact_priorities``) is written by E14-03, but ``search`` /
``detail`` surface the current level read-only so the list view can colour it.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority


class ContactNotFoundError(Exception):
    """No live contact with that id."""


class NumberNotFoundError(Exception):
    """No such number on this contact."""


@dataclass(frozen=True)
class ContactInput:
    name: str
    org: str | None = None
    notes: str | None = None
    quick_dial: bool = False
    bbz_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NumberInput:
    e164: str
    label: str | None = None
    is_primary: bool = False


@dataclass(frozen=True)
class NumberView:
    id: uuid.UUID
    e164: str
    label: str | None
    is_primary: bool


@dataclass(frozen=True)
class ContactView:
    id: uuid.UUID
    name: str
    org: str | None
    notes: str | None
    quick_dial: bool
    bbz_id: uuid.UUID | None
    priority: str | None
    created_at: _dt.datetime
    updated_at: _dt.datetime
    numbers: list[NumberView] = field(default_factory=list)


@dataclass(frozen=True)
class ContactPage:
    items: list[ContactView]
    next_cursor: str | None


def _encode_cursor(name: str, cid: uuid.UUID) -> str:
    raw = json.dumps([name, str(cid)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(raw: str) -> tuple[str, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        return str(payload[0]), uuid.UUID(payload[1])
    except (binascii.Error, ValueError, IndexError, TypeError) as exc:
        raise ValueError("invalid cursor") from exc


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _live(self, stmt: Select[tuple[Contact]]) -> Select[tuple[Contact]]:
        return stmt.where(Contact.deleted_at.is_(None))

    def _scope_filter(self, stmt: Select[tuple[Contact]]) -> Select[tuple[Contact]]:
        return stmt  # E23

    async def get(self, contact_id: uuid.UUID) -> Contact:
        row = (
            await self._s.execute(self._live(select(Contact).where(Contact.id == contact_id)))
        ).scalar_one_or_none()
        if row is None:
            raise ContactNotFoundError(str(contact_id))
        return row

    async def create(self, data: ContactInput) -> Contact:
        contact = Contact(
            name=data.name,
            org=data.org,
            notes=data.notes,
            quick_dial=data.quick_dial,
            bbz_id=data.bbz_id,
        )
        self._s.add(contact)
        await self._s.flush()
        return contact

    async def update(self, contact: Contact, changes: dict[str, object]) -> Contact:
        for key, value in changes.items():
            setattr(contact, key, value)
        await self._s.flush()
        return contact

    async def soft_delete(self, contact: Contact) -> None:
        contact.deleted_at = _dt.datetime.now(_dt.UTC)
        await self._s.flush()

    # --- numbers ---------------------------------------------------------

    async def list_numbers(self, contact_id: uuid.UUID) -> list[ContactNumber]:
        return list(
            (
                await self._s.execute(
                    select(ContactNumber)
                    .where(ContactNumber.contact_id == contact_id)
                    .order_by(ContactNumber.is_primary.desc(), ContactNumber.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    async def add_number(self, contact_id: uuid.UUID, data: NumberInput) -> ContactNumber:
        number = ContactNumber(
            contact_id=contact_id,
            e164=data.e164,
            label=data.label,
            is_primary=data.is_primary,
        )
        self._s.add(number)
        if data.is_primary:
            await self._s.flush()
            await self._demote_other_primaries(contact_id, number.id)
        await self._s.flush()
        return number

    async def get_number(self, contact_id: uuid.UUID, number_id: uuid.UUID) -> ContactNumber:
        row = (
            await self._s.execute(
                select(ContactNumber).where(
                    ContactNumber.id == number_id, ContactNumber.contact_id == contact_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NumberNotFoundError(str(number_id))
        return row

    async def update_number(
        self, number: ContactNumber, changes: dict[str, object]
    ) -> ContactNumber:
        for key, value in changes.items():
            setattr(number, key, value)
        await self._s.flush()
        if changes.get("is_primary"):
            await self._demote_other_primaries(number.contact_id, number.id)
            await self._s.flush()
        return number

    async def remove_number(self, number: ContactNumber) -> None:
        await self._s.delete(number)
        await self._s.flush()

    async def _demote_other_primaries(self, contact_id: uuid.UUID, keep: uuid.UUID) -> None:
        for row in (
            (
                await self._s.execute(
                    select(ContactNumber).where(
                        ContactNumber.contact_id == contact_id,
                        ContactNumber.id != keep,
                        ContactNumber.is_primary.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        ):
            row.is_primary = False

    # --- search / detail ------------------------------------------------

    async def detail(self, contact_id: uuid.UUID) -> ContactView:
        contact = await self.get(contact_id)
        numbers = await self.list_numbers(contact_id)
        priority = await self._s.get(ContactPriority, contact_id)
        return _view(contact, numbers, priority.priority if priority else None)

    async def search(
        self, *, q: str | None = None, limit: int = 50, cursor: str | None = None
    ) -> ContactPage:
        stmt = self._scope_filter(self._live(select(Contact)))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Contact.name.ilike(like),
                    Contact.org.ilike(like),
                    Contact.id.in_(
                        select(ContactNumber.contact_id).where(ContactNumber.e164.ilike(like))
                    ),
                )
            )
        stmt = stmt.order_by(func.lower(Contact.name), Contact.id)
        if cursor is not None:
            c_name, c_id = _decode_cursor(cursor)
            lowered = func.lower(Contact.name)
            stmt = stmt.where(
                or_(
                    lowered > c_name.lower(),
                    (lowered == c_name.lower()) & (Contact.id > c_id),
                )
            )

        contacts = list((await self._s.execute(stmt.limit(limit + 1))).scalars().all())
        nxt: str | None = None
        if len(contacts) > limit:
            contacts = contacts[:limit]
            nxt = _encode_cursor(contacts[-1].name, contacts[-1].id)

        ids = [c.id for c in contacts]
        numbers_by_contact = await self._numbers_for(ids)
        priorities = await self._priorities_for(ids)
        return ContactPage(
            items=[
                _view(c, numbers_by_contact.get(c.id, []), priorities.get(c.id)) for c in contacts
            ],
            next_cursor=nxt,
        )

    async def _numbers_for(
        self, contact_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[ContactNumber]]:
        if not contact_ids:
            return {}
        rows = (
            (
                await self._s.execute(
                    select(ContactNumber)
                    .where(ContactNumber.contact_id.in_(contact_ids))
                    .order_by(ContactNumber.is_primary.desc(), ContactNumber.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        out: dict[uuid.UUID, list[ContactNumber]] = {}
        for row in rows:
            out.setdefault(row.contact_id, []).append(row)
        return out

    async def _priorities_for(self, contact_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not contact_ids:
            return {}
        rows = (
            (
                await self._s.execute(
                    select(ContactPriority).where(ContactPriority.contact_id.in_(contact_ids))
                )
            )
            .scalars()
            .all()
        )
        return {r.contact_id: r.priority for r in rows}


def _view(contact: Contact, numbers: list[ContactNumber], priority: str | None) -> ContactView:
    return ContactView(
        id=contact.id,
        name=contact.name,
        org=contact.org,
        notes=contact.notes,
        quick_dial=contact.quick_dial,
        bbz_id=contact.bbz_id,
        priority=priority,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        numbers=[
            NumberView(id=n.id, e164=n.e164, label=n.label, is_primary=n.is_primary)
            for n in numbers
        ],
    )
