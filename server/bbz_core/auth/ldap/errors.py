"""LDAP failure taxonomy (roadmap E21-03)."""

from __future__ import annotations


class LdapError(Exception):
    """Base: any LDAP configuration / connection / auth failure."""


class LdapConfigError(LdapError):
    """The ``ldap_ad`` provider is not (fully) configured."""


class LdapInsecureError(LdapError):
    """The configured URL is plaintext ``ldap://`` and StartTLS is off — refused."""


class LdapUnavailableError(LdapError):
    """No directory server answered (all pool members down / timed out)."""


class LdapAuthFailed(LdapError):
    """The user DN could not be found, or the user bind was rejected."""
