"""integration_camera_mappings schema — endpoint / alarm source -> camera(s) (E16-05)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.integration_camera_mappings import IntegrationCameraMapping
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _endpoint(s: AsyncSession) -> uuid.UUID:
    e = TechnicalEndpoint(name="Ueberfalltaster SP Nbg", type="panic_button")
    s.add(e)
    await s.flush()
    eid = e.id
    await s.commit()
    return eid


async def test_a_mapping_can_be_anchored_on_an_endpoint(s: AsyncSession) -> None:
    eid = await _endpoint(s)
    s.add(IntegrationCameraMapping(endpoint_id=eid, camera_external_ref="CAM-SP-NBG-01"))
    await s.commit()
    row = (await s.execute(select(IntegrationCameraMapping))).scalar_one()
    assert row.endpoint_id == eid
    assert row.alarm_source_external_id is None
    assert row.ordinal == 0


async def test_a_mapping_can_be_anchored_on_an_external_alarm_source(s: AsyncSession) -> None:
    s.add(
        IntegrationCameraMapping(
            alarm_source_external_id="CODA-ALARM-4711",
            camera_external_ref="CAM-SP-NBG-02",
            ordinal=1,
            provider_instance_id="coda-mock-1",
        )
    )
    await s.commit()
    row = (await s.execute(select(IntegrationCameraMapping))).scalar_one()
    assert row.endpoint_id is None
    assert row.alarm_source_external_id == "CODA-ALARM-4711"
    assert row.ordinal == 1
    assert row.provider_instance_id == "coda-mock-1"


async def test_a_mapping_with_no_anchor_is_rejected(s: AsyncSession) -> None:
    s.add(IntegrationCameraMapping(camera_external_ref="CAM-ORPHAN"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_a_mapping_may_carry_both_anchors_at_once(s: AsyncSession) -> None:
    eid = await _endpoint(s)
    s.add(
        IntegrationCameraMapping(
            endpoint_id=eid,
            alarm_source_external_id="CODA-ALARM-4711",
            camera_external_ref="CAM-1",
        )
    )
    await s.commit()
    row = (await s.execute(select(IntegrationCameraMapping))).scalar_one()
    assert row.endpoint_id == eid and row.alarm_source_external_id == "CODA-ALARM-4711"


async def test_mappings_cascade_when_the_endpoint_is_deleted(s: AsyncSession) -> None:
    eid = await _endpoint(s)
    s.add(IntegrationCameraMapping(endpoint_id=eid, camera_external_ref="CAM-1"))
    s.add(IntegrationCameraMapping(endpoint_id=eid, camera_external_ref="CAM-2", ordinal=1))
    await s.commit()

    await s.delete(await s.get(TechnicalEndpoint, eid))
    await s.commit()
    left = (await s.execute(select(IntegrationCameraMapping))).scalars().all()
    assert left == []


def test_table_is_registered_and_camera_ref_is_a_plain_string() -> None:
    md = Base.metadata.tables
    assert "integration_camera_mappings" in md
    cols = md["integration_camera_mappings"].columns
    # the camera reference is a normalized handle, not a vendor object id / blob
    assert str(cols["camera_external_ref"].type) == "VARCHAR(200)"
    referred = {fk.column.table.name for fk in md["integration_camera_mappings"].foreign_keys}
    assert referred == {"technical_endpoints"}
