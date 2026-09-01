"""LDAP / AD connection + search configuration (roadmap E21-03)."""

from __future__ import annotations

from dataclasses import dataclass

#: attribute → the claim it fills on the resolved identity
DEFAULT_UID_ATTR = "uid"
DEFAULT_NAME_ATTR = "cn"
DEFAULT_MAIL_ATTR = "mail"


@dataclass(frozen=True)
class LdapConfig:
    #: one or more ``ldaps://host:636`` (preferred) or ``ldap://host:389`` URLs,
    #: comma-separated in the setting; a plain URL is only allowed with
    #: ``start_tls=True``
    urls: tuple[str, ...]
    #: service-account DN used to search for the user before the user bind
    bind_dn: str
    bind_password: str
    user_search_base: str
    #: ``%s`` is replaced with the (escaped) login name
    user_filter: str = "(uid=%s)"
    #: enumerate every account (no ``%s``) — used by the directory sync (E21-04)
    user_list_filter: str = "(objectClass=inetOrgPerson)"
    #: page size for the sync's paged search
    page_size: int = 500
    group_search_base: str = ""
    #: ``%s`` is the user's DN
    group_filter: str = "(&(objectClass=groupOfNames)(member=%s))"
    uid_attr: str = DEFAULT_UID_ATTR
    name_attr: str = DEFAULT_NAME_ATTR
    mail_attr: str = DEFAULT_MAIL_ATTR
    #: negotiate StartTLS on a plain connection (ignored for ``ldaps://``)
    start_tls: bool = True
    #: verify the server certificate (MUST stay true in production)
    tls_verify: bool = True
    #: CA bundle path for verification, or "" for the system store
    tls_ca_file: str = ""
    connect_timeout: int = 5
    #: how a group name is derived from its DN (``cn=X,ou=..`` → ``X``)
    group_name_from_dn: bool = True

    @property
    def has_group_search(self) -> bool:
        return bool(self.group_search_base)
