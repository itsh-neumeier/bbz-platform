"""E23-09: the audit-log hash chain — sealing, verification, tamper detection."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.repositories.audit_chain import GENESIS, AuditChainService


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "audit-chain-test-secret-at-least-32-b!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_AUDIT_HASH_CHAIN_ENABLED", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _emit(s: AsyncSession, n: int) -> None:
    async with s.begin():
        for _ in range(n):
            await AuditService(s).write(
                AuditAction.LOGIN_SUCCEEDED, actor_client_id=f"c-{uuid.uuid4().hex[:8]}"
            )


@pytest.fixture
async def db_session(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def test_seal_builds_a_continuous_verified_chain(db_session: AsyncSession) -> None:
    await _emit(db_session, 5)
    sealed = await AuditChainService(db_session).seal()
    assert sealed.sealed == 5

    result = await AuditChainService(db_session).verify()
    assert result.ok and result.checked == 5
    assert result.head_hash == sealed.head_hash

    links = await AuditChainService(db_session).export()
    assert [link.seq for link in links] == [1, 2, 3, 4, 5]
    assert links[0].prev_hash == GENESIS
    assert links[1].prev_hash == links[0].row_hash


async def test_a_second_seal_continues_the_chain(db_session: AsyncSession) -> None:
    await _emit(db_session, 3)
    first = await AuditChainService(db_session).seal()
    await _emit(db_session, 2)
    second = await AuditChainService(db_session).seal()

    assert second.sealed == 2 and second.head_seq == 5
    links = await AuditChainService(db_session).export()
    assert links[3].prev_hash == first.head_hash  # link 4 chains off link 3
    assert (await AuditChainService(db_session).verify()).ok


async def test_seal_is_idempotent_when_nothing_is_new(db_session: AsyncSession) -> None:
    await _emit(db_session, 2)
    await AuditChainService(db_session).seal()
    again = await AuditChainService(db_session).seal()
    assert again.sealed == 0


async def test_tampering_with_a_sealed_row_is_detected(db_session: AsyncSession) -> None:
    await _emit(db_session, 4)
    await AuditChainService(db_session).seal()

    # rewrite a row's payload, bypassing the append-only trigger like a DBA could
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(text("UPDATE audit_events SET reason = 'tampered' WHERE seq = 3"))

    result = await AuditChainService(db_session).verify()
    assert not result.ok
    assert result.first_bad_seq == 3
    assert "hashes to row_hash" in (result.detail or "")


async def test_deleting_a_sealed_row_is_detected(db_session: AsyncSession) -> None:
    await _emit(db_session, 4)
    await AuditChainService(db_session).seal()

    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(text("DELETE FROM audit_events WHERE seq = 2"))

    result = await AuditChainService(db_session).verify()
    assert not result.ok and result.first_bad_seq == 2


async def test_the_worker_tick_seals_and_alarms_on_a_break(db_session: AsyncSession) -> None:
    from bbz_core.workers.registry import _audit_chain_tick

    await _emit(db_session, 3)
    # tick 1: seals cleanly, no alarm
    assert await _audit_chain_tick() == 3
    await db_session.rollback()
    rows = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_events WHERE action = 'AUDIT_INTEGRITY_ALERT'")
        )
    ).scalar_one()
    assert rows == 0

    # break the chain, then force another tick (bypass the interval gate)
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(text("UPDATE audit_events SET node_id = 'evil' WHERE seq = 2"))
        await db_session.execute(
            text("UPDATE audit_chain_links SET sealed_at = now() - interval '1 hour'")
        )

    assert await _audit_chain_tick() == 0
    await db_session.rollback()
    alert = (
        await db_session.execute(
            text(
                "SELECT after FROM audit_events WHERE action = 'AUDIT_INTEGRITY_ALERT' "
                "ORDER BY seq DESC LIMIT 1"
            )
        )
    ).scalar_one()
    assert alert["first_bad_seq"] == 2


async def test_disabled_chain_seals_nothing(db_session: AsyncSession) -> None:
    from bbz_core.workers.registry import _audit_chain_tick

    os.environ["BBZ_AUDIT_HASH_CHAIN_ENABLED"] = "false"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    try:
        await _emit(db_session, 2)
        assert await _audit_chain_tick() == 0
        await db_session.rollback()
        n = (await db_session.execute(text("SELECT count(*) FROM audit_chain_links"))).scalar_one()
        assert n == 0
    finally:
        os.environ.pop("BBZ_AUDIT_HASH_CHAIN_ENABLED", None)
        settings_mod.get_settings.cache_clear()


async def test_the_chain_api_needs_the_permission_and_returns_links(
    client: httpx.AsyncClient, db: object
) -> None:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    s = db
    assert isinstance(s, AsyncSession)
    assert (await client.get("/api/v1/audit/chain")).status_code == 401

    u = User(display_name="Auditor")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="auditor")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key="r-aud", name="R")
    s.add(role)
    await s.flush()
    perm = Permission(key="system.audit.view", area="system")
    s.add(perm)
    await s.flush()
    s.add(RolePermission(role_id=role.id, permission_id=perm.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()

    await _emit(s, 3)
    await AuditChainService(s).seal()

    await client.post(
        "/api/v1/auth/login", json={"username": "auditor", "password": "Wolke7-Bahnhof!x"}
    )
    r = await client.get("/api/v1/audit/chain")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert len(body["links"]) >= 3
    assert body["links"][0]["prev_hash"] == GENESIS
