"""Admin: runtime app settings (ADR-0031 / #720, part of #718).

A DB overlay over the env-based ``Settings``. ``GET`` returns every overridable
key grouped, with its **effective** value and where that value comes from
(``database`` / ``environment`` / ``default``). ``PUT`` writes the overrides for
one group.

Gated on ``system.settings.manage``. Every write is one ``SETTING_CHANGED``
audit row. Secret-valued keys are read-only here (``configured`` only) and
rejected on write — they stay with the ``SecretProvider`` (ADR-0019).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.repositories.settings_store import GroupView, SettingsStore

router = APIRouter(prefix="/admin/settings", tags=["admin"])


class SettingOut(BaseModel):
    key: str
    name: str
    label: str
    help: str
    kind: str
    secret: bool
    value: Any = None
    configured: bool | None = None
    source: str
    overridden: bool


class SettingGroupOut(BaseModel):
    group: str
    label: str
    items: list[SettingOut]


class SettingsOut(BaseModel):
    groups: list[SettingGroupOut]


class SettingsUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(min_length=1)


class SettingsUpdateOut(BaseModel):
    updated: list[str]
    groups: list[SettingGroupOut]


def _render(groups: list[GroupView]) -> list[SettingGroupOut]:
    return [
        SettingGroupOut(
            group=g.group,
            label=g.label,
            items=[
                SettingOut(
                    key=i.key,
                    name=i.name,
                    label=i.label,
                    help=i.help,
                    kind=i.kind,
                    secret=i.secret,
                    value=i.value,
                    configured=i.configured,
                    source=i.source,
                    overridden=i.overridden,
                )
                for i in g.items
            ],
        )
        for g in groups
    ]


@router.get("", response_model=SettingsOut)
async def get_settings_overview(
    _: AuthContext = Depends(require("system.settings.manage")),
    session: AsyncSession = Depends(db_session),
) -> SettingsOut:
    return SettingsOut(groups=_render(await SettingsStore(session).snapshot()))


@router.put("/{group}", response_model=SettingsUpdateOut)
async def update_settings_group(
    group: str,
    body: SettingsUpdateIn,
    ctx: AuthContext = Depends(require("system.settings.manage")),
    session: AsyncSession = Depends(db_session),
) -> SettingsUpdateOut:
    store = SettingsStore(session)
    updated = await store.apply(group, body.values, actor_id=ctx.user_id)
    return SettingsUpdateOut(updated=updated, groups=_render(await store.snapshot()))
