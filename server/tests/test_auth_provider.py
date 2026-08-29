"""Auth-provider contract + registry (no live database)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from bbz_core.auth import (
    AuthenticatedIdentity,
    AuthProvider,
    AuthProviderRegistry,
    CredentialKind,
    EntraOidcAuthProvider,
    LdapAdAuthProvider,
    LocalAuthProvider,
    LocalAuthResult,
    PasswordAuthProvider,
    UnknownAuthProviderError,
)
from bbz_core.auth.hashing import hash_password
from bbz_core.auth.local import CredentialRecord


@pytest.fixture(autouse=True)
def _cheap_argon2() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


class FakeLocalStore:
    def __init__(self) -> None:
        self.uid = uuid.uuid4()
        self.aid = uuid.uuid4()

    async def get_by_username(self, username: str) -> CredentialRecord | None:
        if username != "alice":
            return None
        return CredentialRecord(
            user_id=self.uid,
            auth_identity_id=self.aid,
            password_hash=hash_password("S3cret-passphrase!"),
            must_change=False,
            failed_attempts=0,
            locked_until=None,
            user_active=True,
        )

    async def record_failure(self, aid: uuid.UUID, *, locked_until: object) -> None: ...
    async def reset_failures(self, aid: uuid.UUID) -> None: ...
    async def update_hash(self, aid: uuid.UUID, new_hash: str) -> None: ...
    async def set_password(self, aid: uuid.UUID, new_hash: str, *, must_change: bool) -> None: ...

    async def get_identity(self, subject: str) -> AuthenticatedIdentity | None:
        if subject == "alice":
            return AuthenticatedIdentity(provider="local", subject="alice")
        return None

    async def resolve(
        self, identity: AuthenticatedIdentity, *, provision: bool
    ) -> uuid.UUID | None:
        return self.uid if identity.subject == "alice" else None


def test_local_provider_satisfies_protocols() -> None:
    p = LocalAuthProvider(FakeLocalStore())
    assert isinstance(p, AuthProvider)
    assert isinstance(p, PasswordAuthProvider)
    caps = p.capabilities()
    assert caps.credential_kind is CredentialKind.PASSWORD
    assert caps.password_change is True


def test_external_stubs_have_caps_but_raise() -> None:
    for stub in (EntraOidcAuthProvider(), LdapAdAuthProvider()):
        assert isinstance(stub, AuthProvider)
        assert stub.capabilities().directory_sync is True
    assert (
        EntraOidcAuthProvider().capabilities().credential_kind is CredentialKind.EXTERNAL_REDIRECT
    )
    assert LdapAdAuthProvider().capabilities().credential_kind is CredentialKind.DIRECTORY_BIND


async def test_external_stub_get_identity_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await EntraOidcAuthProvider().get_identity("x")


async def test_local_provider_authenticate_password() -> None:
    p = LocalAuthProvider(FakeLocalStore())
    ok = await p.authenticate_password("alice", "S3cret-passphrase!")
    assert ok.result is LocalAuthResult.SUCCESS and ok.identity is not None
    bad = await p.authenticate_password("alice", "nope")
    assert bad.result is LocalAuthResult.BAD_CREDENTIALS and bad.identity is None


def test_registry_always_has_local_and_looks_up() -> None:
    reg = AuthProviderRegistry([LocalAuthProvider(FakeLocalStore())])
    assert "local" in reg.names()
    assert isinstance(reg.default(), PasswordAuthProvider)
    with pytest.raises(UnknownAuthProviderError):
        reg.get("entra_oidc")


def test_registry_rejects_construction_without_local() -> None:
    with pytest.raises(ValueError, match="local"):
        AuthProviderRegistry([EntraOidcAuthProvider()])


def test_registry_build_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BBZ_AUTH_PROVIDERS", '["ldap_ad"]')
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    reg = AuthProviderRegistry.build(FakeLocalStore())  # type: ignore[arg-type]
    assert set(reg.names()) == {"local", "ldap_ad"}
    settings_mod.get_settings.cache_clear()
