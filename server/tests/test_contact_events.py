"""Contract: every contact CUD operation -> exactly one domain event + audit
row, and the audit references the event and carries the field diff (E14-05)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent

_ALL = ["contacts.view", "contacts.create", "contacts.edit", "contacts.delete"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "contact-events-secret-at-least-32-byte-ok!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key=f"r-{username}", name="R")
    s.add(role)
    await s.flush()
    for key in perms:
        p = Permission(key=key, area=key.split(".")[0])
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


@pytest.fixture
async def api(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_user(s, "op", _ALL)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "op", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200
    yield client, s


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def _events(s: AsyncSession, cid: str) -> list[dict]:
    await s.rollback()
    rows = (
        await s.execute(
            select(DomainEvent.event_type, DomainEvent.event_seq, DomainEvent.payload)
            .where(DomainEvent.aggregate_id == cid, DomainEvent.aggregate_type == "contact")
            .order_by(DomainEvent.event_seq.asc())
        )
    ).all()
    return [{"event_type": t, "event_seq": q, "payload": p} for t, q, p in rows]


async def _audits(s: AsyncSession, cid: str) -> list[dict]:
    await s.rollback()
    rows = (
        await s.execute(
            select(
                AuditEvent.action,
                AuditEvent.before,
                AuditEvent.after,
                AuditEvent.event_seq_ref,
            )
            .where(AuditEvent.target_type == "contact", AuditEvent.target_id == cid)
            .order_by(AuditEvent.occurred_at_utc.asc())
        )
    ).all()
    return [{"action": a, "before": b, "after": af, "event_seq_ref": r} for a, b, af, r in rows]


async def _create(client: httpx.AsyncClient, **over: object) -> str:
    body: dict[str, object] = {"name": "Kontakt", "org": "Org"}
    body.update(over)
    r = await client.post("/api/v1/contacts", json=body, headers=_cmd())
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_create_emits_one_event_and_one_linked_audit(api: tuple) -> None:
    client, s = api
    cid = await _create(client, name="Neu AG", numbers=[{"e164": "+49911500123"}])

    events = await _events(s, cid)
    audits = await _audits(s, cid)
    assert [e["event_type"] for e in events] == ["CONTACT_CREATED"]
    assert [a["action"] for a in audits] == ["CONTACT_CREATED"]
    assert audits[0]["event_seq_ref"] == events[0]["event_seq"]
    assert events[0]["payload"]["name"] == "Neu AG"
    assert events[0]["payload"]["number_count"] == 1


async def test_update_emits_one_event_with_a_field_diff(api: tuple) -> None:
    client, s = api
    cid = await _create(client, name="Alt", org="Alt AG")

    r = await client.patch(f"/api/v1/contacts/{cid}", json={"name": "Neu", "org": None})
    assert r.status_code == 200

    events = [e for e in await _events(s, cid) if e["event_type"] == "CONTACT_UPDATED"]
    audits = [a for a in await _audits(s, cid) if a["action"] == "CONTACT_UPDATED"]
    assert len(events) == 1 and len(audits) == 1
    assert events[0]["payload"]["changes"] == {
        "name": {"from": "Alt", "to": "Neu"},
        "org": {"from": "Alt AG", "to": None},
    }
    assert audits[0]["before"] == {"name": "Alt", "org": "Alt AG"}
    assert audits[0]["after"] == {"name": "Neu", "org": None}
    assert audits[0]["event_seq_ref"] == events[0]["event_seq"]


async def test_a_no_op_patch_emits_nothing(api: tuple) -> None:
    client, s = api
    cid = await _create(client, name="Same")
    r = await client.patch(f"/api/v1/contacts/{cid}", json={"name": "Same"})
    assert r.status_code == 200

    assert [e["event_type"] for e in await _events(s, cid)] == ["CONTACT_CREATED"]
    assert [a["action"] for a in await _audits(s, cid)] == ["CONTACT_CREATED"]


async def test_delete_emits_one_event_and_one_linked_audit(api: tuple) -> None:
    client, s = api
    cid = await _create(client, name="Weg")

    assert (await client.delete(f"/api/v1/contacts/{cid}")).status_code == 204

    events = [e for e in await _events(s, cid) if e["event_type"] == "CONTACT_DELETED"]
    audits = [a for a in await _audits(s, cid) if a["action"] == "CONTACT_DELETED"]
    assert len(events) == 1 and len(audits) == 1
    assert events[0]["payload"]["name"] == "Weg"
    assert audits[0]["event_seq_ref"] == events[0]["event_seq"]


async def test_each_number_operation_emits_one_contact_updated_event(api: tuple) -> None:
    client, s = api
    cid = await _create(client)

    r = await client.post(f"/api/v1/contacts/{cid}/numbers", json={"e164": "+49911111111"})
    nid = r.json()["id"]
    await client.patch(f"/api/v1/contacts/{cid}/numbers/{nid}", json={"label": "Zentrale"})
    await client.delete(f"/api/v1/contacts/{cid}/numbers/{nid}")

    updates = [e for e in await _events(s, cid) if e["event_type"] == "CONTACT_UPDATED"]
    audit_updates = [a for a in await _audits(s, cid) if a["action"] == "CONTACT_UPDATED"]
    assert len(updates) == 3
    assert len(audit_updates) == 3
    assert [set(e["payload"]["changes"]["numbers"]) for e in updates] == [
        {"added"},
        {"updated", "label"},
        {"removed"},
    ]
    for e, a in zip(updates, audit_updates, strict=True):
        assert a["event_seq_ref"] == e["event_seq"]


async def test_every_contact_event_type_is_in_the_payload_schema() -> None:
    from bbz_event_schemas import known_event_types

    assert {"CONTACT_CREATED", "CONTACT_UPDATED", "CONTACT_DELETED"} <= known_event_types()
