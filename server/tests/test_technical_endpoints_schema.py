"""technical_endpoints / technical_endpoint_numbers schema (E15-01)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.technical_endpoints import (
    TechnicalEndpoint,
    TechnicalEndpointNumber,
    TechnicalEndpointType,
)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _endpoint(s: AsyncSession, **kw: object) -> uuid.UUID:
    base: dict[str, object] = {"name": "Siedle Haupteingang", "type": "door_station"}
    base.update(kw)
    e = TechnicalEndpoint(**base)  # type: ignore[arg-type]
    s.add(e)
    await s.flush()
    eid = e.id
    await s.commit()
    return eid


async def test_defaults(s: AsyncSession) -> None:
    e = TechnicalEndpoint(name="BMA Halle 3", type="bma")
    s.add(e)
    await s.commit()
    await s.refresh(e)
    assert e.enabled is True
    assert e.external_source_ids == []
    assert e.active_config_version == 1
    assert e.default_priority is None and e.workflow_selection_policy is None


@pytest.mark.parametrize("t", [t.value for t in TechnicalEndpointType])
async def test_every_declared_type_is_accepted(s: AsyncSession, t: str) -> None:
    s.add(TechnicalEndpoint(name=f"ep-{t}", type=t))
    await s.commit()


async def test_an_unknown_type_is_rejected(s: AsyncSession) -> None:
    s.add(TechnicalEndpoint(name="weird", type="smoke_signal"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_default_priority_is_constrained_but_nullable(s: AsyncSession) -> None:
    s.add(TechnicalEndpoint(name="x", type="custom", default_priority="urgent"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    s.add(TechnicalEndpoint(name="x", type="custom", default_priority="critical"))
    await s.commit()


async def test_jsonb_fields_round_trip(s: AsyncSession) -> None:
    eid = await _endpoint(
        s,
        external_source_ids=["SEP001A2B3C4D5E", "coda:cam-12"],
        workflow_selection_policy={"mode": "latest_published", "template_key": "bma_alarm"},
    )
    e = await s.get(TechnicalEndpoint, eid)
    assert e is not None
    assert e.external_source_ids == ["SEP001A2B3C4D5E", "coda:cam-12"]
    assert e.workflow_selection_policy == {
        "mode": "latest_published",
        "template_key": "bma_alarm",
    }


async def test_numbers_cascade_when_the_endpoint_is_deleted(s: AsyncSession) -> None:
    eid = await _endpoint(s)
    s.add(TechnicalEndpointNumber(endpoint_id=eid, called_pattern="110", cti_route_point="RP_BMA"))
    await s.commit()

    await s.delete(await s.get(TechnicalEndpoint, eid))
    await s.commit()
    left = (
        (
            await s.execute(
                select(TechnicalEndpointNumber).where(TechnicalEndpointNumber.endpoint_id == eid)
            )
        )
        .scalars()
        .all()
    )
    assert left == []


def test_technical_endpoints_are_modelled_separately_from_contacts() -> None:
    """MASTER_PROMPT §29 — technical systems are not phone-book contacts."""
    md = Base.metadata.tables
    assert {"technical_endpoints", "technical_endpoint_numbers", "contacts"} <= set(md)
    for name in ("technical_endpoints", "technical_endpoint_numbers"):
        referred = {fk.column.table.name for fk in md[name].foreign_keys}
        assert "contacts" not in referred and "contact_numbers" not in referred
