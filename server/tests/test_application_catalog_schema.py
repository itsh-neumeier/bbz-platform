"""application_catalog / application_catalog_scopes schema (E10-02)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.application_catalog import (
    ApplicationCatalogEntry,
    ApplicationCatalogScope,
)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _entry(url: str = "https://leidis.example.gov/", **kw: object) -> ApplicationCatalogEntry:
    return ApplicationCatalogEntry(name="LeiDis", url=url, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["ftp://x/", "javascript:alert(1)", "file:///etc/passwd", "leidis"])
async def test_url_must_be_http_or_https(s: AsyncSession, bad: str) -> None:
    s.add(_entry(url=bad))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_https_url_and_defaults(s: AsyncSession) -> None:
    e = _entry(url="HTTPS://ARAMIS.example.gov/app")  # scheme check is case-insensitive
    s.add(e)
    await s.commit()
    await s.refresh(e)
    assert e.launch_mode == "window"
    assert e.enabled is True
    assert e.sort_order == 0
    assert e.version == 1
    assert e.created_at is not None


async def test_launch_mode_is_a_closed_set(s: AsyncSession) -> None:
    s.add(_entry(launch_mode="fullscreen"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    for mode in ("window", "app_window", "tab"):
        e = _entry(launch_mode=mode)
        s.add(e)
        await s.commit()
        await s.rollback()


async def test_scopes_are_optional_and_cascade(s: AsyncSession) -> None:
    e = _entry()
    s.add(e)
    await s.flush()
    app_id = e.app_id
    # an app with no scope rows is valid (visible everywhere)
    await s.commit()

    s.add(ApplicationCatalogScope(app_id=app_id, role_key="sichtleiter"))
    s.add(ApplicationCatalogScope(app_id=app_id, workplace_id=uuid.uuid4()))
    await s.commit()

    entry = await s.get(ApplicationCatalogEntry, app_id)
    assert entry is not None
    await s.delete(entry)
    await s.commit()
    left = (
        (
            await s.execute(
                select(ApplicationCatalogScope).where(ApplicationCatalogScope.app_id == app_id)
            )
        )
        .scalars()
        .all()
    )
    assert left == []
