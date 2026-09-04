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
    LdapError,
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

    def probe(self) -> dict[str, object]:
        """One-shot reachability / TLS / service-bind / sample-search check for
        the admin "test connection" button (#723). Structured booleans + a
        reason; never raises for an operational failure. No user data leaves —
        only a small count."""
        cfg = self._cfg
        out: dict[str, object] = {
            "reachable": False,
            "tls_ok": False,
            "bind_ok": False,
            "sample_count": None,
            "error": None,
        }
        try:
            conn = self._connect(
                _servers(cfg), cfg.bind_dn, cfg.bind_password, who="service account"
            )
        except LdapUnavailableError as exc:
            out["error"] = str(exc)
            return out
        except LdapInsecureError as exc:
            out["reachable"] = True
            out["error"] = str(exc)
            return out
        except (LdapConfigError, LdapAuthFailed, LdapError) as exc:
            # reachable + past TLS; the service bind itself was rejected
            out["reachable"] = True
            out["tls_ok"] = True
            out["error"] = f"service bind failed: {exc}"
            return out
        out.update(reachable=True, tls_ok=True, bind_ok=True)
        try:
            conn.search(
                cfg.user_search_base,
                cfg.user_list_filter,
                attributes=[cfg.uid_attr],
                size_limit=5,
            )
            out["sample_count"] = len(conn.entries)
        except LDAPException as exc:
            out["error"] = f"search failed: {exc}"
        finally:
            conn.unbind()
        return out

    def enumerate_principals(self) -> list[LdapPrincipal]:
        """Every account under ``user_search_base`` (paged), each with its groups.
        Service-bind only — no user binds. For the directory sync (E21-04)."""
        cfg = self._cfg
        servers = _servers(cfg)
        conn = self._connect(servers, cfg.bind_dn, cfg.bind_password, who="service account")
        try:
            found: list[tuple[str, str, str | None, str | None]] = []
            for item in conn.extend.standard.paged_search(
                cfg.user_search_base,
                cfg.user_list_filter,
                attributes=[cfg.uid_attr, cfg.name_attr, cfg.mail_attr],
                paged_size=cfg.page_size,
                generator=True,
            ):
                if item.get("type") != "searchResEntry":
                    continue
                attrs = item.get("attributes") or {}
                dn = str(item.get("dn") or "")
                uid = _first(attrs.get(cfg.uid_attr))
                if dn and uid:
                    name = _first(attrs.get(cfg.name_attr))
                    mail = _first(attrs.get(cfg.mail_attr))
                    found.append((dn, uid, name, mail))
            # the paged search is fully drained — safe to reuse the connection
            return [
                LdapPrincipal(
                    dn=dn,
                    uid=uid,
                    display_name=name,
                    email=mail,
                    groups=self._groups_on(conn, dn),
                )
                for dn, uid, name, mail in found
            ]
        finally:
            conn.unbind()

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
            return self._groups_on(conn, user_dn)
        finally:
            conn.unbind()

    def _groups_on(self, conn: ldap3.Connection, user_dn: str) -> tuple[str, ...]:
        if not self._cfg.has_group_search:
            return ()
        flt = self._cfg.group_filter.replace("%s", escape_filter_chars(user_dn))
        conn.search(self._cfg.group_search_base, flt, attributes=["cn"])
        names: list[str] = []
        for e in conn.entries:
            if self._cfg.group_name_from_dn:
                names.append(_cn_of(str(e.entry_dn)))
            else:
                names.append(str(e["cn"].value))
        return tuple(dict.fromkeys(n for n in names if n))


def _first(value: object) -> str | None:
    if isinstance(value, list | tuple):
        value = value[0] if value else None
    return str(value) if value not in (None, "") else None


def _cn_of(dn: str) -> str:
    for attr, val, _sep in parse_dn(dn):
        if str(attr).lower() == "cn":
            return str(val)
    return dn
