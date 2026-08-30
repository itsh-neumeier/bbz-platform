"""Function-node task kinds (roadmap E05-10, `.ai/WORKFLOW_EPK.md`).

Pure classification. The engine parks a token at every function node; this
module says what the runtime must then do with it:

* **operator** kinds (``manual`` / ``confirmation`` / ``documentation``) block
  progress until an operator completes the step.
* **timer** kinds resume automatically once ``props.duration_seconds`` has
  elapsed (persisted, so a restart does not lose the deadline).
* **auto** kinds (``integration_action`` / ``notification`` / ``event_update``)
  enqueue exactly one typed ``external_action_outbox`` row — never an arbitrary
  script (MASTER_PROMPT §29/§33) — and let the token move on; the side effect
  runs exactly-once through the outbox dispatcher.
"""

from __future__ import annotations

import uuid

OPERATOR_KINDS = frozenset({"manual", "confirmation", "documentation"})
TIMER_KINDS = frozenset({"timer"})
AUTO_KINDS = frozenset({"integration_action", "notification", "event_update"})

#: outbox ``action_type`` per auto kind. The concrete handlers are registered
#: by the integration epics; ``notify`` already ships with the dispatcher.
_OUTBOX_ACTION = {
    "integration_action": "integration",
    "notification": "notify",
    "event_update": "event_update",
}

_DEFAULT_TIMER_SECONDS = 60


class TaskKindError(ValueError):
    pass


def outbox_action(kind: str) -> str:
    try:
        return _OUTBOX_ACTION[kind]
    except KeyError as exc:
        raise TaskKindError(f"{kind!r} is not an auto task kind") from exc


def timer_seconds(props: dict[str, object] | None) -> int:
    raw = (props or {}).get("duration_seconds", _DEFAULT_TIMER_SECONDS)
    try:
        seconds: int = int(raw)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        raise TaskKindError(f"timer props.duration_seconds is not a number: {raw!r}") from None
    if seconds < 0:
        raise TaskKindError("timer props.duration_seconds must not be negative")
    return seconds


def step_dedupe_key(instance_id: uuid.UUID, node_key: str) -> str:
    """Stable across retries: ``instance_id + node + attempt-0`` (E05-10 AC)."""
    return f"workflow-step:{instance_id}:{node_key}:attempt-0"
