"""Scope vocabulary for permission grants (MASTER_PROMPT §12).

Owned here (the authorization layer), persisted by ``bbz_core.infra`` as a
``VARCHAR`` + CHECK on ``role_permissions.scope``.
"""

from __future__ import annotations

import enum


class Scope(enum.StrEnum):
    GLOBAL = "global"
    REGION = "region"
    BBZ = "bbz"
    WORKPLACE = "workplace"
    OWN_EVENTS = "own_events"
    ASSIGNED_EVENTS = "assigned_events"
