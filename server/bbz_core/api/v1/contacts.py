"""Phone-book API (roadmap E14-02).

CRUD + search over contacts and their numbers (MASTER_PROMPT §13.9). Deletion is
**soft**. Creating a contact carries the command envelope (``X-Command-Id``) and
is idempotent on replay. Every change is audited (``CONTACT_CREATED`` /
``CONTACT_UPDATED`` / ``CONTACT_DELETED``); the field-level audit diff and the
domain events are refined in E14-05. Priority assignment is E14-03.

``name`` / ``org`` / number are personally identifiable — ``contacts.view`` and
scope (wired E23) gate reads; writes need ``contacts.create/edit/delete``.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.idempotency import (
    CommandConflictError,
    CommandInProgressError,
    idempotent,
    request_hash,
)
from bbz_core.infra.repositories.contacts import (
    ContactInput,
    ContactNotFoundError,
    ContactRepository,
    ContactView,
    NumberInput,
    NumberNotFoundError,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])

_E164 = r"^\+[1-9][0-9]{1,14}$"


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except (ContactNotFoundError, NumberNotFoundError) as exc:
        raise NotFoundError("contact not found") from exc
    except CommandConflictError as exc:
        raise ConflictError("command id reused with a different body") from exc
    except CommandInProgressError as exc:
        raise ConflictError("an identical command is still being processed") from exc
    except IntegrityError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate == "23505":
            raise ConflictError("this number is already on the contact") from exc
        raise ValidationError("the number is not a valid E.164 string") from exc


class NumberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    e164: str = Field(pattern=_E164, max_length=16)
    label: str | None = Field(default=None, max_length=80)
    is_primary: bool = False


class NumberOut(BaseModel):
    id: uuid.UUID
    e164: str
    label: str | None
    is_primary: bool


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    org: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20_000)
    quick_dial: bool = False
    bbz_id: uuid.UUID | None = None
    numbers: list[NumberIn] = Field(default_factory=list, max_length=50)


class ContactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    org: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20_000)
    quick_dial: bool | None = None
    bbz_id: uuid.UUID | None = None


class NumberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=80)
    is_primary: bool | None = None


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    org: str | None
    notes: str | None
    quick_dial: bool
    bbz_id: uuid.UUID | None
    priority: str | None
    created_at: _dt.datetime
    updated_at: _dt.datetime
    numbers: list[NumberOut]


class ContactPageOut(BaseModel):
    items: list[ContactOut]
    next_cursor: str | None


def _out(view: ContactView) -> ContactOut:
    return ContactOut(
        id=view.id,
        name=view.name,
        org=view.org,
        notes=view.notes,
        quick_dial=view.quick_dial,
        bbz_id=view.bbz_id,
        priority=view.priority,
        created_at=view.created_at,
        updated_at=view.updated_at,
        numbers=[
            NumberOut(id=n.id, e164=n.e164, label=n.label, is_primary=n.is_primary)
            for n in view.numbers
        ],
    )


@router.get("", response_model=ContactPageOut)
async def search_contacts(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    _: AuthContext = Depends(require("contacts.view")),
    session: AsyncSession = Depends(db_session),
) -> ContactPageOut:
    """Phone-book search (§13.9). ``q`` matches name / org (substring,
    case-insensitive) and any number. Alphabetical by name, keyset-paginated —
    pass ``next_cursor`` back as ``cursor``. Soft-deleted contacts are excluded.
    """
    try:
        page = await ContactRepository(session).search(q=q, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise ValidationError("invalid cursor") from exc
    return ContactPageOut(items=[_out(v) for v in page.items], next_cursor=page.next_cursor)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactIn,
    response: Response,
    ctx: AuthContext = Depends(require("contacts.create")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ContactOut:
    rhash = request_hash(body.model_dump(mode="json"))
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint="POST /api/v1/contacts",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                response.status_code = slot.replay.status
                out = ContactOut.model_validate(slot.replay.body)
                response.headers["Location"] = f"/api/v1/contacts/{out.id}"
                return out

            repo = ContactRepository(session)
            async with session.begin():
                contact = await repo.create(
                    ContactInput(
                        name=body.name,
                        org=body.org,
                        notes=body.notes,
                        quick_dial=body.quick_dial,
                        bbz_id=body.bbz_id,
                    )
                )
                contact_id = contact.id
                for n in body.numbers:
                    await repo.add_number(
                        contact_id,
                        NumberInput(e164=n.e164, label=n.label, is_primary=n.is_primary),
                    )
                await AuditService(session).write(
                    AuditAction.CONTACT_CREATED,
                    actor_user_id=ctx.user_id,
                    target_type="contact",
                    target_id=str(contact_id),
                    after={
                        "name": body.name,
                        "org": body.org,
                        "quick_dial": body.quick_dial,
                        "number_count": len(body.numbers),
                    },
                )
            out = _out(await repo.detail(contact_id))
            slot.set_result(status.HTTP_201_CREATED, out.model_dump(mode="json"))

    response.headers["Location"] = f"/api/v1/contacts/{out.id}"
    return out


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(
    contact_id: uuid.UUID,
    _: AuthContext = Depends(require("contacts.view")),
    session: AsyncSession = Depends(db_session),
) -> ContactOut:
    try:
        return _out(await ContactRepository(session).detail(contact_id))
    except ContactNotFoundError as exc:
        raise NotFoundError("contact not found") from exc


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactPatch,
    ctx: AuthContext = Depends(require("contacts.edit")),
    session: AsyncSession = Depends(db_session),
) -> ContactOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("no fields to update")
    await session.rollback()
    repo = ContactRepository(session)
    with _translate():
        async with session.begin():
            contact = await repo.get(contact_id)
            before = {k: getattr(contact, k) for k in changes}
            await repo.update(contact, changes)
            await AuditService(session).write(
                AuditAction.CONTACT_UPDATED,
                actor_user_id=ctx.user_id,
                target_type="contact",
                target_id=str(contact_id),
                before={k: _jsonable(v) for k, v in before.items()},
                after={k: _jsonable(v) for k, v in changes.items()},
            )
    return _out(await repo.detail(contact_id))


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    ctx: AuthContext = Depends(require("contacts.delete")),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Soft-delete. The contact drops out of search and lookups; its numbers and
    priority row stay for the retention window (E23)."""
    await session.rollback()
    repo = ContactRepository(session)
    with _translate():
        async with session.begin():
            contact = await repo.get(contact_id)
            name = contact.name
            await repo.soft_delete(contact)
            await AuditService(session).write(
                AuditAction.CONTACT_DELETED,
                actor_user_id=ctx.user_id,
                target_type="contact",
                target_id=str(contact_id),
                before={"name": name},
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- numbers sub-resource ------------------------------------------------


@router.get("/{contact_id}/numbers", response_model=list[NumberOut])
async def list_numbers(
    contact_id: uuid.UUID,
    _: AuthContext = Depends(require("contacts.view")),
    session: AsyncSession = Depends(db_session),
) -> list[NumberOut]:
    repo = ContactRepository(session)
    try:
        await repo.get(contact_id)
    except ContactNotFoundError as exc:
        raise NotFoundError("contact not found") from exc
    return [
        NumberOut(id=n.id, e164=n.e164, label=n.label, is_primary=n.is_primary)
        for n in await repo.list_numbers(contact_id)
    ]


@router.post("/{contact_id}/numbers", response_model=NumberOut, status_code=status.HTTP_201_CREATED)
async def add_number(
    contact_id: uuid.UUID,
    body: NumberIn,
    ctx: AuthContext = Depends(require("contacts.edit")),
    session: AsyncSession = Depends(db_session),
) -> NumberOut:
    await session.rollback()
    repo = ContactRepository(session)
    with _translate():
        async with session.begin():
            await repo.get(contact_id)
            number = await repo.add_number(
                contact_id,
                NumberInput(e164=body.e164, label=body.label, is_primary=body.is_primary),
            )
            num = NumberOut(
                id=number.id, e164=number.e164, label=number.label, is_primary=number.is_primary
            )
            await AuditService(session).write(
                AuditAction.CONTACT_UPDATED,
                actor_user_id=ctx.user_id,
                target_type="contact",
                target_id=str(contact_id),
                after={"number_added": body.e164},
            )
    return num


@router.patch("/{contact_id}/numbers/{number_id}", response_model=NumberOut)
async def update_number(
    contact_id: uuid.UUID,
    number_id: uuid.UUID,
    body: NumberPatch,
    ctx: AuthContext = Depends(require("contacts.edit")),
    session: AsyncSession = Depends(db_session),
) -> NumberOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("no fields to update")
    await session.rollback()
    repo = ContactRepository(session)
    with _translate():
        async with session.begin():
            number = await repo.get_number(contact_id, number_id)
            await repo.update_number(number, changes)
            num = NumberOut(
                id=number.id, e164=number.e164, label=number.label, is_primary=number.is_primary
            )
            await AuditService(session).write(
                AuditAction.CONTACT_UPDATED,
                actor_user_id=ctx.user_id,
                target_type="contact",
                target_id=str(contact_id),
                after={
                    "number_updated": str(number_id),
                    **{k: _jsonable(v) for k, v in changes.items()},
                },
            )
    return num


@router.delete("/{contact_id}/numbers/{number_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_number(
    contact_id: uuid.UUID,
    number_id: uuid.UUID,
    ctx: AuthContext = Depends(require("contacts.edit")),
    session: AsyncSession = Depends(db_session),
) -> Response:
    await session.rollback()
    repo = ContactRepository(session)
    with _translate():
        async with session.begin():
            number = await repo.get_number(contact_id, number_id)
            await repo.remove_number(number)
            await AuditService(session).write(
                AuditAction.CONTACT_UPDATED,
                actor_user_id=ctx.user_id,
                target_type="contact",
                target_id=str(contact_id),
                after={"number_removed": str(number_id)},
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _jsonable(value: object) -> object:
    return str(value) if isinstance(value, uuid.UUID) else value
