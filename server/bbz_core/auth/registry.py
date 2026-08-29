"""Which auth providers are active, and lookup by name.

``local`` is always present and is the fallback. The rest of the enabled list
comes from ``BBZ_AUTH_PROVIDERS`` (E02-04 acceptance).
"""

from __future__ import annotations

from collections.abc import Iterable

from bbz_core.auth.provider import AuthProvider, PasswordAuthProvider
from bbz_core.auth.providers import (
    EntraOidcAuthProvider,
    LdapAdAuthProvider,
    LocalAuthProvider,
    LocalIdentityStore,
)
from bbz_core.settings import get_settings

_EXTERNAL: dict[str, type[AuthProvider]] = {
    "entra_oidc": EntraOidcAuthProvider,
    "ldap_ad": LdapAdAuthProvider,
}


class UnknownAuthProviderError(KeyError):
    pass


class AuthProviderRegistry:
    def __init__(self, providers: Iterable[AuthProvider]) -> None:
        self._by_name: dict[str, AuthProvider] = {p.name: p for p in providers}
        if "local" not in self._by_name:
            raise ValueError("the 'local' auth provider must always be registered")

    @classmethod
    def build(cls, local_store: LocalIdentityStore) -> AuthProviderRegistry:
        wanted = list(dict.fromkeys(["local", *get_settings().auth_providers]))
        providers: list[AuthProvider] = []
        for name in wanted:
            if name == "local":
                providers.append(LocalAuthProvider(local_store))
            elif name in _EXTERNAL:
                providers.append(_EXTERNAL[name]())
            else:
                raise UnknownAuthProviderError(name)
        return cls(providers)

    def names(self) -> list[str]:
        return list(self._by_name)

    def get(self, name: str) -> AuthProvider:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise UnknownAuthProviderError(name) from exc

    def default(self) -> PasswordAuthProvider:
        """The always-available local password provider (fallback)."""
        provider = self._by_name["local"]
        if not isinstance(provider, PasswordAuthProvider):  # invariant guard
            raise TypeError("'local' provider must support password authentication")
        return provider
