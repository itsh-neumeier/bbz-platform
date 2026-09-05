"""The permission-key catalog and scope vocabulary.

This is the single source of truth for *which* permission keys exist
(``docs/domain/permission-catalog.md`` / MASTER_PROMPT §12). Roles are data,
but the set of keys they may grant is fixed code — an unknown key is a bug,
never a silent allow.

Seed data for the ``permissions`` table (E02-14) is generated from ``CATALOG``.
"""

from __future__ import annotations

from bbz_core.authorization.scopes import Scope

CATALOG: dict[str, tuple[str, ...]] = {
    "events": (
        "events.view",
        "events.create",
        "events.accept",
        "events.acknowledge",
        "events.open",
        "events.edit",
        "events.assign",
        "events.takeover",
        "events.close",
        "events.archive",
        "events.reactivate",
        "events.postprocess",
        "events.export",
    ),
    "workflows": (
        "workflows.view",
        "workflows.execute",
        "workflows.override",
        "workflows.manage_templates",
    ),
    "calls": (
        "calls.view",
        "calls.answer",
        "calls.dial",
        "calls.hangup",
        "calls.hold",
        "calls.transfer",
        "calls.document",
        "calls.view_history",
        # machine-to-machine: a telephony provider / CTI gateway posting
        # normalized events (E11-03). Not granted to any human built-in role.
        "calls.ingest_provider_events",
        # dev/CI/E2E only: drive the mock provider's scenario helpers over
        # HTTP (E11-05's own "Szenarien per API/Config auslösbar"). 404s on
        # any non-mock provider. Not granted to any human built-in role.
        "calls.simulate_mock_scenario",
    ),
    "contacts": (
        "contacts.view",
        "contacts.create",
        "contacts.edit",
        "contacts.delete",
        "contacts.assign_priority",
    ),
    "monitor": (
        "monitor.view",
        "monitor.route",
        "monitor.reset_standard",
        "monitor.manage_profiles",
    ),
    "weather": ("weather.view", "weather.create_event"),
    "users_roles": (
        "users.view",
        "users.manage",
        "roles.view",
        "roles.manage",
        "permissions.manage",
    ),
    "integrations": (
        "integrations.view",
        "integrations.configure",
        "integrations.enable_disable",
        "integrations.diagnostics",
    ),
    "system": (
        "system.audit.view",
        "system.cluster.view",
        "system.cluster.manage",
        "system.settings.manage",
    ),
    "bku": (
        "bku.status.view",
        "bku.apps.launch",
        "bku.apps.close",
        "bku.session.logout",
        "bku.device.restart",
        "bku.catalog.view",
        "bku.catalog.manage",
        "bku.agent.manage",
    ),
    "agents": ("agents.manage",),  # BBZ client agents (roadmap E09-08)
    "door_technical": (
        "door.view",
        "door.answer",
        "door.open",
        "door.configure",
        "technical_endpoints.view",
        "technical_endpoints.manage",
    ),
}

PERMISSION_KEYS: frozenset[str] = frozenset(k for keys in CATALOG.values() for k in keys)

#: keys that are only ever held by service accounts (machine-to-machine), never
#: by a human built-in role.
MACHINE_KEYS: frozenset[str] = frozenset(
    {"calls.ingest_provider_events", "calls.simulate_mock_scenario"}
)

SCOPES: frozenset[str] = frozenset(s.value for s in Scope)


class PermissionKeyError(KeyError):
    """A permission key that is not in the catalog was used."""


def assert_known(key: str) -> None:
    if key not in PERMISSION_KEYS:
        raise PermissionKeyError(key)


def area_of(key: str) -> str | None:
    return key.split(".", 1)[0] if key in PERMISSION_KEYS else None
