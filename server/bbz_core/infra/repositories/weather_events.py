"""Create a BBZ event from a DWD weather warning (roadmap E18-08).

The operator picks a warning on the Wetterlage page, chooses a priority and adds
an operational assessment; this turns it into a normal BBZ event (``source =
"weather"``) linked back to the warning via ``weather_alert_events``. Idempotent
on the command id — a repeated click makes exactly one event. Not automatic:
there is deliberately no path that creates an event without an operator (§10).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.events import EventAggregate, EventPriority
from bbz_core.infra.event_stream import notify_event_appended
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.weather import WeatherAlert
from bbz_core.infra.models.weather_alert_events import WeatherAlertEvent
from bbz_core.infra.repositories.events import EventRepository

_ENDPOINT = "POST /api/v1/weather/alerts/{id}/create-event"
_MAX_ASSESSMENT = 20_000


def _assessment_block(assessment: str | None) -> str | None:
    return f"— Bewertung —\n{assessment}" if assessment else None


class WeatherAlertNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class WeatherEventResult:
    event_id: uuid.UUID
    weather_alert_id: uuid.UUID
    source_ref: str
    priority: str
    created: bool

    def as_body(self) -> dict[str, object]:
        return {
            "event_id": str(self.event_id),
            "weather_alert_id": str(self.weather_alert_id),
            "source_ref": self.source_ref,
            "priority": self.priority,
            "created": self.created,
        }

    @classmethod
    def from_body(cls, body: dict[str, object] | None) -> WeatherEventResult:
        b = body or {}
        return cls(
            event_id=uuid.UUID(str(b["event_id"])),
            weather_alert_id=uuid.UUID(str(b["weather_alert_id"])),
            source_ref=str(b["source_ref"]),
            priority=str(b["priority"]),
            created=bool(b.get("created", True)),
        )


class WeatherEventService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_from_alert(
        self,
        *,
        alert_id: uuid.UUID,
        priority: EventPriority,
        assessment: str | None,
        command_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> WeatherEventResult:
        assessment = (assessment or "").strip()[:_MAX_ASSESSMENT] or None
        rhash = request_hash(
            {"alert_id": str(alert_id), "priority": priority.value, "assessment": assessment}
        )
        async with idempotent(
            self._s,
            command_id=command_id,
            endpoint=_ENDPOINT,
            request_hash=rhash,
            user_id=actor_id,
        ) as slot:
            if slot.replay is not None:
                return WeatherEventResult.from_body(slot.replay.body)

            await self._s.rollback()
            alert = await self._s.get(WeatherAlert, alert_id)
            if alert is None:
                raise WeatherAlertNotFoundError(str(alert_id))
            title = (alert.headline or f"{alert.type} — {alert.region}")[:300]
            parts = [p for p in (alert.description, _assessment_block(assessment)) if p]
            description = "\n\n".join(parts) or None
            source_ref, region = alert.source_ref, alert.region

            event_id = uuid.uuid4()
            agg = EventAggregate.create(
                event_id=event_id,
                title=title,
                priority=priority,
                actor_id=actor_id,
                description=description,
                source="weather",
            )
            await self._s.rollback()  # close the read tx from .get() before begin()
            async with self._s.begin():
                await EventRepository(self._s).add(agg, actor_id=actor_id, command_id=command_id)
                self._s.add(
                    WeatherAlertEvent(
                        weather_alert_id=alert_id,
                        event_id=event_id,
                        source_ref=source_ref,
                        assessment=assessment,
                        created_by=actor_id,
                    )
                )
                await AuditService(self._s).write(
                    AuditAction.WEATHER_EVENT_CREATED,
                    actor_user_id=actor_id,
                    target_type="event",
                    target_id=str(event_id),
                    after={
                        "weather_alert_id": str(alert_id),
                        "source_ref": source_ref,
                        "region": region,
                        "priority": priority.value,
                        "has_assessment": assessment is not None,
                    },
                )

            await notify_event_appended()
            result = WeatherEventResult(
                event_id=event_id,
                weather_alert_id=alert_id,
                source_ref=source_ref,
                priority=priority.value,
                created=True,
            )
            slot.set_result(201, result.as_body())
            return result

    async def events_for_alert(self, alert_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            await self._s.execute(
                select(WeatherAlertEvent.event_id).where(
                    WeatherAlertEvent.weather_alert_id == alert_id
                )
            )
        ).scalars()
        return list(rows)
