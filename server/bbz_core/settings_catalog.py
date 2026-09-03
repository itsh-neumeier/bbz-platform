"""The whitelist of runtime-overridable settings (ADR-0031 / #720).

Every key an operator may change from the Administration area is declared here —
its group, type, validation, and (for env-backed keys) the :class:`Settings`
field it falls back to when there is no ``app_settings`` row. A key that is not
in this catalog cannot be read or written through the settings store; the
override surface is a reviewed code change, exactly like the permission catalog.

Secret-valued keys (``secret=True``) are listed so the UI can show whether they
are configured, but the store never persists them — they stay with the
``SecretProvider`` (ADR-0019).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SettingKind = Literal["str", "bool", "int", "str_list"]


@dataclass(frozen=True)
class SettingSpec:
    key: str  # admin-facing key, "<group>.<name>"
    group: str
    kind: SettingKind
    label: str
    #: the ``Settings`` attribute this key falls back to (environment / code
    #: default). ``None`` ⇒ a store-only concept whose fallback is ``default``.
    field: str | None = None
    default: object = None
    help: str = ""
    secret: bool = False
    choices: tuple[str, ...] | None = None
    min: int | None = None
    max: int | None = None
    #: a ``str`` value for this key may not be set to the empty string
    required: bool = False

    @property
    def name(self) -> str:
        return self.key.split(".", 1)[1]


#: group key → human label (also fixes the group order in the API response)
GROUPS: dict[str, str] = {
    "instance": "Instanz",
    "directory": "Verzeichnis (LDAP)",
    "integrations": "Integrationen",
}

CATALOG: tuple[SettingSpec, ...] = (
    SettingSpec(
        "instance.name",
        "instance",
        "str",
        "Name der BBZ-Instanz",
        default="BBZ / 3-S-Zentrale",
        help="Wird im Operator-UI angezeigt, z. B. „BBZ Nürnberg“.",
        required=True,
    ),
    SettingSpec(
        "instance.short_name",
        "instance",
        "str",
        "Kurzname",
        default="BBZ",
        help="Kompakte Form für enge UI-Bereiche.",
        required=True,
    ),
    SettingSpec(
        "directory.ldap_url",
        "directory",
        "str",
        "LDAP-URL(s)",
        field="ldap_url",
        help="ldaps:// oder ldap:// (+ StartTLS). Mehrere per Komma für Failover.",
    ),
    SettingSpec(
        "directory.ldap_bind_dn",
        "directory",
        "str",
        "Bind-DN",
        field="ldap_bind_dn",
    ),
    SettingSpec(
        "directory.ldap_bind_password",
        "directory",
        "str",
        "Bind-Passwort",
        field="ldap_bind_password",
        secret=True,
        help="Über den Secret-Store gepflegt (ADR-0019), nicht hier.",
    ),
    SettingSpec(
        "directory.ldap_user_search_base",
        "directory",
        "str",
        "User-Search-Base",
        field="ldap_user_search_base",
    ),
    SettingSpec(
        "integrations.weather",
        "integrations",
        "str",
        "Wetter-Provider",
        field="weather_integration_id",
        help="Integration, die die Wetterlage bedient.",
    ),
    SettingSpec(
        "integrations.monitor",
        "integrations",
        "str",
        "Monitor-Provider",
        field="monitor_integration_id",
    ),
    SettingSpec(
        "integrations.telephony",
        "integrations",
        "str",
        "Telefonie-Provider",
        field="telephony_integration_id",
    ),
    SettingSpec(
        "integrations.video",
        "integrations",
        "str",
        "Video-Provider",
        field="video_integration_id",
    ),
)

SPEC_BY_KEY: dict[str, SettingSpec] = {s.key: s for s in CATALOG}
KEYS_BY_GROUP: dict[str, tuple[SettingSpec, ...]] = {
    g: tuple(s for s in CATALOG if s.group == g) for g in GROUPS
}


class UnknownSettingKey(KeyError):
    """A settings key that is not in the catalog was used."""
