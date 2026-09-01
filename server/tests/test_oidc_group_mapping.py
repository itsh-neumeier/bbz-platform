"""OIDC group → BBZ role mapping + JIT policy (roadmap E21-02).

The mapping is admin config; on each external login the user's mapped roles are
reconciled from the ``groups`` claim — added, and removed when the group is gone,
without ever touching a manually-assigned role.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.auth_mapping import AuthGroupMapping, ExternalRoleAssignment
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

_ISSUER = "https://idp.test/tenant"
_CLIENT = "bbz-test-client"
_REDIRECT = "https://bbz.local/cb"


@pytest.fixture(autouse=True)
def _oidc_env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing
    from bbz_core.infra.repositories import oidc_login as oidc_mod

    os.environ.update(
        {
            "BBZ_OIDC_ENTRA_ISSUER": _ISSUER,
            "BBZ_OIDC_ENTRA_CLIENT_ID": _CLIENT,
            "BBZ_OIDC_ENTRA_REDIRECT_URI": _REDIRECT,
            "BBZ_JWT_SECRET": "oidc-map-test-secret-at-least-32-bytes!!",
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_SESSION_COOKIE_SECURE": "false",
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    oidc_mod._META_CACHE.clear()
    yield
    for k in (
        "BBZ_OIDC_ENTRA_ISSUER",
        "BBZ_OIDC_ENTRA_CLIENT_ID",
        "BBZ_OIDC_ENTRA_REDIRECT_URI",
        "BBZ_OIDC_JIT_PROVISIONING",
        "BBZ_OIDC_JIT_DEFAULT_ROLE",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _role(s: AsyncSession, key: str) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        r = Role(key=key, name=key.title())
        s.add(r)
        await s.flush()
        p = Permission(key=f"{key}.view", area=key)
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=r.id, permission_id=p.id, scope="global"))
        rid = r.id
    return rid


async def _user(s: AsyncSession, name: str = "extern", *, link: bool = True) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name=name)
        s.add(u)
        await s.flush()
        if link:
            s.add(AuthIdentity(user_id=u.id, provider="entra_oidc", subject=f"sub-{name}"))
        uid = u.id
    return uid


async def _add_mappings(s: AsyncSession, *rules: tuple[str, str]) -> None:
    await s.rollback()
    async with s.begin():
        for group, role_key in rules:
            s.add(AuthGroupMapping(provider="entra_oidc", external_group=group, role_key=role_key))


async def _user_role_keys(s: AsyncSession, user_id: uuid.UUID) -> set[str]:
    await s.rollback()
    rows = (
        await s.execute(
            select(Role.key).select_from(UserRole).join(Role).where(UserRole.user_id == user_id)
        )
    ).scalars()
    return set(rows)


# --- the reconcile, called directly -----------------------------------


async def test_sync_adds_and_removes_mapped_roles(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.auth_group_mapping import GroupMappingService

    await _role(s, "disponent")
    await _role(s, "sichtleiter")
    uid = await _user(s)
    await _add_mappings(s, ("grp-disp", "disponent"), ("grp-sicht", "sichtleiter"))
    svc = GroupMappingService(s)

    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=("grp-disp",))
    assert await _user_role_keys(s, uid) == {"disponent"}

    await svc.sync_user_roles(
        user_id=uid, provider="entra_oidc", external_groups=("grp-disp", "grp-sicht")
    )
    assert await _user_role_keys(s, uid) == {"disponent", "sichtleiter"}

    # the disponent group is gone on the next login
    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=("grp-sicht",))
    assert await _user_role_keys(s, uid) == {"sichtleiter"}


async def test_sync_never_touches_a_manually_assigned_role(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.auth_group_mapping import GroupMappingService

    manual = await _role(s, "administrator")
    await _role(s, "disponent")
    uid = await _user(s)
    await _add_mappings(s, ("grp-disp", "disponent"))
    async with s.begin():
        s.add(UserRole(user_id=uid, role_id=manual, granted_by=uid))  # by hand

    svc = GroupMappingService(s)
    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=("grp-disp",))
    assert await _user_role_keys(s, uid) == {"administrator", "disponent"}
    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=())
    assert await _user_role_keys(s, uid) == {"administrator"}  # only the mapped one dropped


async def test_sync_is_a_no_op_when_nothing_changed(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.auth_group_mapping import GroupMappingService

    await _role(s, "disponent")
    uid = await _user(s)
    await _add_mappings(s, ("g", "disponent"))
    svc = GroupMappingService(s)
    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=("g",))
    n1 = (await s.execute(select(func.count()).select_from(AuditEvent))).scalar_one()
    await svc.sync_user_roles(user_id=uid, provider="entra_oidc", external_groups=("g",))
    n2 = (await s.execute(select(func.count()).select_from(AuditEvent))).scalar_one()
    assert n1 == n2  # second sync wrote no audit rows


# --- through the full OIDC login --------------------------------------


class _MockIdP:
    def __init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwks(self) -> list[dict[str, Any]]:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
        return [jwk]

    def id_token(self, *, nonce: str, sub: str, groups: list[str]) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": _ISSUER,
                "sub": sub,
                "aud": _CLIENT,
                "iat": now,
                "exp": now + 300,
                "nonce": nonce,
                "name": "Ext",
                "groups": groups,
            },
            key=self._key,
            algorithm="RS256",
            headers={"kid": "k1"},
        )


class _StubHttp:
    def __init__(self, idp: _MockIdP, **_: Any) -> None:
        self._idp = idp
        self.codes: dict[str, str] = {}

    async def get_json(self, url: str) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": _ISSUER,
                "authorization_endpoint": f"{_ISSUER}/authorize",
                "token_endpoint": f"{_ISSUER}/token",
                "jwks_uri": f"{_ISSUER}/keys",
            }
        return {"keys": self._idp.jwks()}

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {"id_token": self.codes[data["code"]], "access_token": "at"}


async def _login(s: AsyncSession, idp: _MockIdP, *, sub: str, groups: list[str]) -> uuid.UUID:
    from urllib.parse import parse_qs, urlparse

    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    svc = OidcLoginService(s, http=_StubHttp(idp))
    url = await svc.begin("entra_oidc")
    q = parse_qs(urlparse(url).query)
    code = uuid.uuid4().hex
    svc._http.codes[code] = idp.id_token(nonce=q["nonce"][0], sub=sub, groups=groups)
    return await svc.complete("entra_oidc", code=code, state=q["state"][0])


async def test_group_claim_drives_roles_across_logins(s: AsyncSession) -> None:
    await _role(s, "disponent")
    await _role(s, "sichtleiter")
    uid = await _user(s, "known")
    await _add_mappings(s, ("A", "disponent"), ("B", "sichtleiter"))
    idp = _MockIdP()

    assert await _login(s, idp, sub="sub-known", groups=["A"]) == uid
    assert await _user_role_keys(s, uid) == {"disponent"}

    await _login(s, idp, sub="sub-known", groups=["B"])
    assert await _user_role_keys(s, uid) == {"sichtleiter"}  # A dropped, B added


async def test_jit_user_gets_only_the_mapped_roles(s: AsyncSession) -> None:
    from bbz_core import settings as settings_mod

    os.environ["BBZ_OIDC_JIT_PROVISIONING"] = "true"
    settings_mod.get_settings.cache_clear()
    await _role(s, "disponent")
    await _role(s, "administrator")
    await _add_mappings(s, ("ops", "disponent"))
    idp = _MockIdP()

    uid = await _login(s, idp, sub="fresh-sub", groups=["ops", "unmapped-group"])
    assert await _user_role_keys(s, uid) == {"disponent"}  # only the mapped one
    await s.rollback()
    assert (
        await s.execute(select(func.count()).select_from(ExternalRoleAssignment))
    ).scalar_one() == 1


# --- admin API -------------------------------------------------------


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_JWT_SECRET"] = "oidc-map-test-secret-at-least-32-bytes!!"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _admin(s: AsyncSession, perms: list[str]) -> None:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import LocalCredential

    u = User(display_name="Admin")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="admin")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key="r-admin", name="R")
    s.add(role)
    await s.flush()
    for key in perms:
        p = Permission(key=key, area=key.split(".")[0])
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login_admin(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def test_mapping_crud_is_gated_and_audited(env: tuple) -> None:
    client, s = env
    await _role(s, "disponent")
    await _admin(s, ["roles.manage"])
    await _login_admin(client)

    r = await client.post(
        "/api/v1/auth/group-mappings",
        json={"provider": "entra_oidc", "external_group": "grp-a", "role_key": "disponent"},
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    listed = (await client.get("/api/v1/auth/group-mappings")).json()["mappings"]
    assert [m["external_group"] for m in listed] == ["grp-a"]

    # a duplicate rule → 409
    dup = await client.post(
        "/api/v1/auth/group-mappings",
        json={"provider": "entra_oidc", "external_group": "grp-a", "role_key": "disponent"},
    )
    assert dup.status_code == 409

    # an unknown role → 422
    bad = await client.post(
        "/api/v1/auth/group-mappings",
        json={"provider": "entra_oidc", "external_group": "x", "role_key": "nope"},
    )
    assert bad.status_code == 422

    assert (await client.delete(f"/api/v1/auth/group-mappings/{mid}")).status_code == 204

    await s.rollback()
    changes = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "AUTH_MAPPING_CHANGED")
        )
    ).scalar_one()
    assert changes == 2  # one create + one delete


async def test_mapping_write_needs_roles_manage(env: tuple) -> None:
    client, s = env
    await _admin(s, ["roles.view"])
    await _login_admin(client)
    r = await client.post(
        "/api/v1/auth/group-mappings",
        json={"provider": "entra_oidc", "external_group": "g", "role_key": "x"},
    )
    assert r.status_code == 403
