"""Line status service (roadmap E11-07).

Keeps the ``lines`` table current from the normalized ``LINE_IN_SERVICE`` /
``LINE_OUT_OF_SERVICE`` provider events (fed in by ``telephony_ingest``), and
appends a matching ``LINE_*`` domain event so an outage shows up on the event
stream and in ``GET /api/v1/lines``. Not audited (roadmap E11-07).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.event_log import append_event
from bbz_core.infra.models.telephony import Line

_LINE_EVENTS: dict[str, str] = {
    "LINE_IN_SERVICE": "in_service",
    "LINE_OUT_OF_SERVICE": "out_of_service",
}


class LineStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def on_line_event(self, event: dict[str, Any]) -> None:
        state = _LINE_EVENTS.get(event["event_type"])
        external_id = event.get("line_id")
        if state is None or not external_id:
            return

        provider = event["provider"]
        line = (
            await self._s.execute(
                select(Line).where(Line.provider == provider, Line.external_id == external_id)
            )
        ).scalar_one_or_none()
        if line is None:
            line = Line(provider=provider, external_id=external_id, state=state)
            self._s.add(line)
            await self._s.flush()
        elif line.state == state:
            return  # no change — do not emit a spurious event
        else:
            line.state = state

        await append_event(
            self._s,
            aggregate_type="line",
            aggregate_id=line.id,
            event_type=event["event_type"],
            payload={"provider": provider, "external_id": external_id, "state": state},
        )
