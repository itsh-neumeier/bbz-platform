"""Per-provider OIDC configuration + the discovered IdP metadata (roadmap E21-01)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OidcConfig:
    """Static config for one OIDC provider (e.g. ``entra_oidc``). The client
    secret is optional — a public client uses PKCE alone."""

    provider: str
    issuer: str
    client_id: str
    redirect_uri: str
    client_secret: str | None = None
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    #: override the well-known URL (default: ``<issuer>/.well-known/openid-configuration``)
    discovery_url: str | None = None

    @property
    def well_known(self) -> str:
        return self.discovery_url or f"{self.issuer.rstrip('/')}/.well-known/openid-configuration"

    @property
    def scope_param(self) -> str:
        scopes = ("openid", *[s for s in self.scopes if s != "openid"])
        return " ".join(dict.fromkeys(scopes))


@dataclass(frozen=True)
class OidcMetadata:
    """The subset of the IdP's discovery document the flow uses."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    id_token_signing_alg_values_supported: tuple[str, ...] = field(default_factory=tuple)
