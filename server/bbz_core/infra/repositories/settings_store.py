"""Runtime settings store — the DB overlay over env config (ADR-0031 / #720).

``effective(key)`` resolves **DB override → environment → code default**. A short
process-wide TTL cache keeps the read cheap and lets a change propagate
cluster-wide within the TTL without a message bus. ``apply(...)`` validates
against :mod:`bbz_core.settings_catalog`, writes the override rows and emits one
``SETTING_CHANGED`` audit row per call.

Secret-valued keys are never persisted here: ``apply`` rejects them and
``snapshot`` reports only whether they are configured (via ``Settings``, which
already reads ``BBZ_*`` env + the secrets dir).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.errors import ValidationError
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.app_settings import AppSetting
from bbz_core.settings import Settings, get_settings
from bbz_core.settings_catalog import (
    GROUPS,
    KEYS_BY_GROUP,
    SPEC_BY_KEY,
    SettingSpec,
)

# --- process-wide TTL cache of the override rows ---------------------------
_TTL_SECONDS = 10.0
_cache: dict[str, Any] = {}
_cache_at: float = 0.0


@dataclass(frozen=True)
class SettingView:
    key: str
    name: str
    label: str
    help: str
    kind: str
    secret: bool
    #: effective value (``None`` for a secret — see ``configured``)
    value: Any
    #: for a secret key: is a value available from the environment / secrets dir
    configured: bool | None
    #: ``database`` | ``environment`` | ``default``
    source: str
    overridden: bool


@dataclass(frozen=True)
class GroupView:
    group: str
    label: str
    items: list[SettingView]


def _field_default(field: str) -> Any:
    info = Settings.model_fields.get(field)
    if info is None:  # pragma: no cover - guarded by the catalog test
        raise KeyError(field)
    return info.get_default(call_default_factory=True)


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    """Validate ``raw`` against ``spec`` and return the stored representation."""
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise ValidationError(f"{spec.key}: expected a boolean")
        return raw
    if spec.kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValidationError(f"{spec.key}: expected an integer")
        if spec.min is not None and raw < spec.min:
            raise ValidationError(f"{spec.key}: must be ≥ {spec.min}")
        if spec.max is not None and raw > spec.max:
            raise ValidationError(f"{spec.key}: must be ≤ {spec.max}")
        return raw
    if spec.kind == "str_list":
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            raise ValidationError(f"{spec.key}: expected a list of strings")
        return [x.strip() for x in raw if x.strip()]
    # str
    if not isinstance(raw, str):
        raise ValidationError(f"{spec.key}: expected a string")
    val = raw.strip()
    if spec.required and not val:
        raise ValidationError(f"{spec.key}: must not be empty")
    if spec.choices is not None and val and val not in spec.choices:
        raise ValidationError(f"{spec.key}: must be one of {', '.join(spec.choices)}")
    return val


class SettingsStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- read --------------------------------------------------------

    async def _overrides(self) -> dict[str, Any]:
        global _cache_at
        now = time.monotonic()
        if _cache_at and now - _cache_at < _TTL_SECONDS:
            return _cache
        rows = (await self._s.execute(select(AppSetting.key, AppSetting.value))).all()
        _cache.clear()
        _cache.update({row.key: row.value for row in rows})
        _cache_at = now
        return _cache

    async def effective(self, key: str) -> Any:
        """The value that applies right now: DB override → env → code default."""
        spec = SPEC_BY_KEY[key]
        overrides = await self._overrides()
        if key in overrides:
            return overrides[key]
        return self._fallback(spec)

    @staticmethod
    def _fallback(spec: SettingSpec) -> Any:
        if spec.field is not None:
            return getattr(get_settings(), spec.field)
        return spec.default

    @staticmethod
    def _source(spec: SettingSpec, *, overridden: bool) -> str:
        if overridden:
            return "database"
        if spec.field is None:
            return "default"
        current = getattr(get_settings(), spec.field)
        try:
            return "default" if current == _field_default(spec.field) else "environment"
        except KeyError:  # pragma: no cover
            return "environment"

    async def snapshot(self) -> list[GroupView]:
        overrides = await self._overrides()
        settings = get_settings()
        out: list[GroupView] = []
        for group, label in GROUPS.items():
            items: list[SettingView] = []
            for spec in KEYS_BY_GROUP[group]:
                overridden = spec.key in overrides
                if spec.secret:
                    configured = bool(spec.field is not None and getattr(settings, spec.field, ""))
                    items.append(
                        SettingView(
                            key=spec.key,
                            name=spec.name,
                            label=spec.label,
                            help=spec.help,
                            kind=spec.kind,
                            secret=True,
                            value=None,
                            configured=configured,
                            source="environment" if configured else "default",
                            overridden=False,
                        )
                    )
                    continue
                items.append(
                    SettingView(
                        key=spec.key,
                        name=spec.name,
                        label=spec.label,
                        help=spec.help,
                        kind=spec.kind,
                        secret=False,
                        value=overrides[spec.key] if overridden else self._fallback(spec),
                        configured=None,
                        source=self._source(spec, overridden=overridden),
                        overridden=overridden,
                    )
                )
            out.append(GroupView(group=group, label=label, items=items))
        return out

    # --- write ------------------------------------------------------

    async def apply(
        self, group: str, values: dict[str, Any], *, actor_id: uuid.UUID | None
    ) -> list[str]:
        """Validate + persist the overrides in ``values`` for ``group``.

        Idempotent: a key already at the requested value is a no-op. Returns the
        keys that actually changed.
        """
        if group not in GROUPS:
            raise ValidationError(f"unknown settings group: {group}")
        group_keys = {s.key for s in KEYS_BY_GROUP[group]}

        coerced: dict[str, Any] = {}
        for key, raw in values.items():
            if key not in group_keys:
                raise ValidationError(f"unknown setting for group {group!r}: {key}")
            spec = SPEC_BY_KEY[key]
            if spec.secret:
                raise ValidationError(
                    f"{key} is a secret — manage it via the secret store (ADR-0019), "
                    "not the settings API"
                )
            coerced[key] = _coerce(spec, raw)

        await self._s.rollback()
        changes: dict[str, dict[str, Any]] = {}
        async with self._s.begin():
            for key, new in coerced.items():
                spec = SPEC_BY_KEY[key]
                row = await self._s.get(AppSetting, key)
                before = row.value if row is not None else self._fallback(spec)
                if new == before:
                    continue
                await self._s.execute(
                    pg_insert(AppSetting)
                    .values(key=key, value=new, updated_by=actor_id)
                    .on_conflict_do_update(
                        index_elements=["key"],
                        set_={"value": new, "updated_by": actor_id, "updated_at": func.now()},
                    )
                )
                changes[key] = {"from": before, "to": new}
            if changes:
                await AuditService(self._s).write(
                    AuditAction.SETTING_CHANGED,
                    actor_user_id=actor_id,
                    target_type="settings_group",
                    target_id=group,
                    before={k: v["from"] for k, v in changes.items()},
                    after={k: v["to"] for k, v in changes.items()},
                )
        if changes:
            self.invalidate()
        return sorted(changes)

    @classmethod
    def invalidate(cls) -> None:
        global _cache_at
        _cache_at = 0.0
