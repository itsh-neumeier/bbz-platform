"""Blocking LDAP client — bind-authenticate + resolve groups (roadmap E21-03).

The transport is **always encrypted**: an ``ldaps://`` URL, or a plain URL with
StartTLS negotiated before the bind. A plain URL with StartTLS off is refused
outright (:class:`LdapInsecureError`). Multiple URLs form a failover pool.

``ldap3`` is synchronous — the auth provider runs :meth:`authenticate` in a
worker thread.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass

import ldap3
from ldap3.core.exceptions import (
    LDAPBindError,
    LDAPException,
    LDAPSocketOpenError,
    LDAPStartTLSError,
)
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from bbz_core.auth.ldap.config import LdapConfig
from bbz_core.auth.ldap.errors import (
    LdapAuthFailed,
    LdapConfigError,
    LdapInsecureError,
    LdapUnavailableError,
)


@dataclass(frozen=True)
class LdapPrincipal:
    dn: str
    uid: str
    display_name: str | None
    email: str | None
    groups: tuple[str, ...]


def _tls(cfg: LdapConfig) -> ldap3.Tls:
    return ldap3.Tls(
        validate=ssl.CERT_REQUIRED if cfg.tls_verify else ssl.CERT_NONE,
        ca_certs_file=cfg.tls_ca_file or None,
    )


def _servers(cfg: LdapConfig) -> ldap3.Server | ldap3.ServerPool:
    tls = _tls(cfg)
    built = []
    for url in cfg.urls:
        use_ssl = url.lower().startswith("ldaps://")
        if not use_ssl and not cfg.start_tls:
            raise LdapInsecureError(f"plaintext LDAP without StartTLS is refused: {url}")
        built.append(
            ldap3.Server(url, use_ssl=use_ssl, tls=tls, connect_timeout=cfg.connect_timeout)
        )
    if not built:
        raise LdapConfigError("no LDAP URLs configured")
    if len(built) == 1:
        return built[0]
    return ldap3.ServerPool(built, ldap3.FIRST, active=True, exhaust=True)


class LdapClient:
    def __init__(self, cfg: LdapConfig) -> None:
        self._cfg = cfg

    def authenticate(self, username: str, password: str) -> LdapPrincipal:
        """Service-bind → find the user → bind as the user (the actual auth) →
        collect group memberships. Raises :class:`LdapAuthFailed` for any
        credential problem, :class:`LdapUnavailableError` if no server answered."""
        if not username or not password:
            raise LdapAuthFailed("empty credentials")
        cfg = self._cfg
        servers = _servers(cfg)

        svc = self._connect(servers, cfg.bind_dn, cfg.bind_password, who="service account")
        try:
            user_dn, attrs = self._find_user(svc, username)
        finally:
            svc.unbind()

        user_conn = self._connect(servers, user_dn, password, who="user", auth_failure=True)
        user_conn.unbind()  # the successful bind was the authentication

        groups = self._groups(servers, user_dn)
        return LdapPrincipal(
            dn=user_dn,
            uid=_first(attrs.get(cfg.uid_attr)) or username,
            display_name=_first(attrs.get(cfg.name_attr)),
            email=_first(attrs.get(cfg.mail_attr)),
            groups=groups,
        )

    # --- steps -------------------------------------------------

    def _connect(
        self,
        servers: ldap3.Server | ldap3.ServerPool,
        dn: str,
        pw: str,
        *,
        who: str,
        auth_failure: bool = False,
    ) -> ldap3.Connection:
        conn = ldap3.Connection(
            servers,
            user=dn,
            password=pw,
            auto_bind=False,
            receive_timeout=self._cfg.connect_timeout,
        )
        ok = False
        try:
            if not conn.server.ssl and self._cfg.start_tls:
                conn.open()
                conn.start_tls()
            if not conn.bind():
                raise LDAPBindError(conn.result)
            ok = True
        except LDAPSocketOpenError as exc:
            raise LdapUnavailableError(f"no LDAP server reachable ({who}): {exc}") from exc
        except LDAPStartTLSError as exc:
            raise LdapInsecureError(f"StartTLS failed: {exc}") from exc
        except LDAPBindError as exc:
            if auth_failure:
                raise LdapAuthFailed("invalid directory credentials") from exc
            raise LdapConfigError(f"{who} bind rejected") from exc
        except LDAPException as exc:  # normalise any other ldap3 error
            raise LdapUnavailableError(f"LDAP error ({who}): {exc}") from exc
        finally:
            if not ok:
                conn.unbind()  # release the socket open()/start_tls() may have created
        return conn

    def _find_user(self, conn: ldap3.Connection, username: str) -> tuple[str, dict[str, object]]:
        flt = self._cfg.user_filter.replace("%s", escape_filter_chars(username))
        ok = conn.search(
            self._cfg.user_search_base,
            flt,
            attributes=[self._cfg.uid_attr, self._cfg.name_attr, self._cfg.mail_attr],
        )
        if not ok or not conn.entries:
            raise LdapAuthFailed("no such directory user")
        entry = conn.entries[0]
        attrs = {a: entry[a].value for a in entry.entry_attributes}
        return str(entry.entry_dn), attrs

    def _groups(self, servers: ldap3.Server | ldap3.ServerPool, user_dn: str) -> tuple[str, ...]:
        if not self._cfg.has_group_search:
            return ()
        conn = self._connect(
            servers, self._cfg.bind_dn, self._cfg.bind_password, who="group search"
        )
        try:
            flt = self._cfg.group_filter.replace("%s", escape_filter_chars(user_dn))
            conn.search(self._cfg.group_search_base, flt, attributes=["cn"])
            names: list[str] = []
            for e in conn.entries:
                if self._cfg.group_name_from_dn:
                    names.append(_cn_of(str(e.entry_dn)))
                else:
                    names.append(str(e["cn"].value))
            return tuple(dict.fromkeys(n for n in names if n))
        finally:
            conn.unbind()


def _first(value: object) -> str | None:
    if isinstance(value, list | tuple):
        value = value[0] if value else None
    return str(value) if value not in (None, "") else None


def _cn_of(dn: str) -> str:
    for attr, val, _sep in parse_dn(dn):
        if str(attr).lower() == "cn":
            return str(val)
    return dn
