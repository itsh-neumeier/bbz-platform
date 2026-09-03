"""Admin: integration overview (#724, part of #718).

Per domain (telephony · video · weather · monitor): the discoverable adapters
(from the manifests), which one is selected (settings store → env, #720), and
its current health. The selection is changed through the generic settings API
(`PUT /admin/settings/integrations`, audited `SETTING_CHANGED`); adapter
credentials stay with the `SecretProvider` (ADR-0019).

A provider instance is cached for the process lifetime (a stateful CTI/mock
session must be a singleton), so a changed selection takes effect on the next
restart — same as an environment change.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.repositories.integration_health import IntegrationHealthService
from bbz_core.infra.repositories.settings_store import SettingsStore
from bbz_core.integrations_host.registry import IntegrationRegistry

router = APIRouter(prefix="/admin/integrations", tags=["admin"])

#: the domains with a runtime-selectable provider (settings key `integrations.<domain>`)
_DOMAINS = ("telephony", "video", "weather", "monitor")


class AdapterOut(BaseModel):
    id: str
    name: str
    mock: bool
    version: str


class DomainHealthOut(BaseModel):
    state: str
    summary: str


class DomainIntegrationOut(BaseModel):
    domain: str
    setting_key: str
    active_id: str
    source: str  # database | environment | default
    available: list[AdapterOut]
    #: true when the active adapter ships only as a mock (missing vendor docs)
    active_is_mock: bool
    health: DomainHealthOut | None


class IntegrationsOverviewOut(BaseModel):
    domains: list[DomainIntegrationOut]


@router.get("", response_model=IntegrationsOverviewOut)
async def integrations_overview(
    _: AuthContext = Depends(require("integrations.view")),
    session: AsyncSession = Depends(db_session),
) -> IntegrationsOverviewOut:
    manifests = IntegrationRegistry.discover()
    by_domain: dict[str, list[AdapterOut]] = {}
    for lm in manifests:
        m = lm.manifest
        by_domain.setdefault(m.domain, []).append(
            AdapterOut(id=m.id, name=m.name, mock=bool(m.mock), version=m.version)
        )

    store = SettingsStore(session)
    snapshot = {i.key: i for g in await store.snapshot() for i in g.items}

    health_by_id: dict[str, DomainHealthOut] = {}
    try:
        for v in await IntegrationHealthService(session).refresh():
            health_by_id[v.integration_id] = DomainHealthOut(state=v.state, summary=v.summary)
    except Exception:  # health is best-effort — never blocks the overview
        pass

    out: list[DomainIntegrationOut] = []
    for domain in _DOMAINS:
        key = f"integrations.{domain}"
        item = snapshot.get(key)
        active_id = str(item.value) if item and item.value is not None else ""
        available = sorted(by_domain.get(domain, []), key=lambda a: a.id)
        out.append(
            DomainIntegrationOut(
                domain=domain,
                setting_key=key,
                active_id=active_id,
                source=item.source if item else "default",
                available=available,
                active_is_mock=any(a.id == active_id and a.mock for a in available),
                health=health_by_id.get(active_id),
            )
        )
    return IntegrationsOverviewOut(domains=out)
