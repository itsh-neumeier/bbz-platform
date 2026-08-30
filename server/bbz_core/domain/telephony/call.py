"""The call aggregate (roadmap E11-04).

Pure, following the ``EventAggregate`` pattern (E03-04): normalized provider
events drive the state; ``collect_events()`` drains the business domain events
to append + audit. An out-of-order or post-terminal provider event is absorbed
without crashing — telephony providers are messy and a reconnect can replay a
truncated sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bbz_core.domain.telephony.state import (
    TERMINAL,
    CallDirection,
    CallState,
    business_event_for,
    provider_target_state,
)


@dataclass(frozen=True)
class CallDomainEvent:
    type: str
    payload: dict[str, Any]


@dataclass
class CallAggregate:
    bbz_call_id: str
    direction: CallDirection
    state: CallState = CallState.OFFERED
    source_call_id: str | None = None
    line_id: str | None = None
    _pending: list[CallDomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def start(
        cls,
        *,
        bbz_call_id: str,
        direction: CallDirection,
        source_call_id: str | None = None,
        line_id: str | None = None,
    ) -> CallAggregate:
        return cls(
            bbz_call_id=bbz_call_id,
            direction=direction,
            state=CallState.OFFERED,
            source_call_id=source_call_id,
            line_id=line_id,
        )

    def apply_provider_event(self, normalized_event_type: str) -> None:
        target = provider_target_state(normalized_event_type)
        if target is None:
            return  # not a call transition (line / device / CTI event)
        if self.state in TERMINAL:
            return  # the call already ended — ignore a late / replayed event
        if target is self.state:
            return  # idempotent (a re-delivered event of the current state)

        old = self.state
        self.state = target
        be = business_event_for(old, target)
        if be is not None:
            self._emit(be, {"from": old.value, "to": target.value})

    def collect_events(self) -> list[CallDomainEvent]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def _emit(self, event_type: str, extra: dict[str, Any]) -> None:
        payload: dict[str, Any] = {
            "bbz_call_id": self.bbz_call_id,
            "source_call_id": self.source_call_id,
            "direction": self.direction.value,
            "line_id": self.line_id,
            **extra,
        }
        self._pending.append(CallDomainEvent(type=event_type, payload=payload))
