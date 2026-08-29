"""The five built-in roles and their default permission grants (E02-14).

Deployments create their own roles; these are a sensible starting point
(MASTER_PROMPT §12). All grants are scope ``global`` — narrow per site later.
"""

from __future__ import annotations

from bbz_core.authorization.keys import PERMISSION_KEYS

_VIEW_ONLY = frozenset(k for k in PERMISSION_KEYS if k.rsplit(".", 1)[-1] == "view")

_ADMINISTRATOR = PERMISSION_KEYS  # everything

_SICHTLEITER = frozenset(
    {
        *[k for k in PERMISSION_KEYS if k.startswith("events.")],
        "workflows.view",
        "workflows.execute",
        "workflows.override",
        *[k for k in PERMISSION_KEYS if k.startswith("calls.")],
        *[k for k in PERMISSION_KEYS if k.startswith("contacts.")],
        *[k for k in PERMISSION_KEYS if k.startswith("monitor.")],
        "weather.view",
        "weather.create_event",
        *[k for k in PERMISSION_KEYS if k.startswith("bku.")],
        *[k for k in PERMISSION_KEYS if k.startswith("door.")],
        "technical_endpoints.view",
        "integrations.view",
        "integrations.diagnostics",
        "system.audit.view",
        "system.cluster.view",
        "users.view",
        "roles.view",
    }
)

_DISPONENT = frozenset(
    {
        "events.view",
        "events.create",
        "events.accept",
        "events.acknowledge",
        "events.open",
        "events.edit",
        "events.assign",
        "events.takeover",
        "events.close",
        "events.postprocess",
        "workflows.view",
        "workflows.execute",
        "calls.view",
        "calls.answer",
        "calls.dial",
        "calls.hangup",
        "calls.hold",
        "calls.transfer",
        "calls.document",
        "calls.view_history",
        "contacts.view",
        "contacts.create",
        "contacts.edit",
        "contacts.assign_priority",
        "monitor.view",
        "monitor.route",
        "weather.view",
        "weather.create_event",
        "door.view",
        "door.answer",
        "door.open",
        "bku.status.view",
        "bku.apps.launch",
        "bku.apps.close",
        "technical_endpoints.view",
    }
)

_NACHBEARBEITUNG = frozenset(
    {
        "events.view",
        "events.postprocess",
        "events.export",
        "workflows.view",
        "calls.view_history",
        "contacts.view",
        "weather.view",
        "system.audit.view",
    }
)

BUILTIN_ROLES: dict[str, tuple[str, frozenset[str]]] = {
    "administrator": ("Administrator", _ADMINISTRATOR),
    "sichtleiter": ("Sichtleiter", _SICHTLEITER),
    "disponent": ("Disponent", _DISPONENT),
    "nachbearbeitung": ("Nachbearbeitung", _NACHBEARBEITUNG),
    "nur_lesen": ("Nur Lesen", _VIEW_ONLY),
}
