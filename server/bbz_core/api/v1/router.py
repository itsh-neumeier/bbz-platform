from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from bbz_core import __version__
from bbz_core.api.v1.audit import router as audit_router
from bbz_core.api.v1.auth import router as auth_router
from bbz_core.api.v1.calls import router as calls_router
from bbz_core.api.v1.client_popups import router as client_popups_router
from bbz_core.api.v1.coda_alarm_sources import router as coda_alarm_sources_router
from bbz_core.api.v1.contacts import router as contacts_router
from bbz_core.api.v1.door_action_profiles import router as door_action_profiles_router
from bbz_core.api.v1.events import router as events_router
from bbz_core.api.v1.integrations import router as integrations_router
from bbz_core.api.v1.lines import router as lines_router
from bbz_core.api.v1.presence import router as presence_router
from bbz_core.api.v1.rbac import router as rbac_router
from bbz_core.api.v1.system import router as system_router
from bbz_core.api.v1.technical_endpoints import router as technical_endpoints_router
from bbz_core.api.v1.telephony import router as telephony_router
from bbz_core.api.v1.totp import router as totp_router
from bbz_core.api.v1.trigger_diagnostics import router as trigger_diagnostics_router
from bbz_core.api.v1.trigger_rules import router as trigger_rules_router
from bbz_core.api.v1.users import router as users_router
from bbz_core.api.v1.workflows import router as workflows_router
from bbz_core.integrations_host.registry import IntegrationRegistry
from bbz_core.settings import get_settings

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
api_v1.include_router(audit_router)
api_v1.include_router(events_router)
api_v1.include_router(calls_router)
api_v1.include_router(contacts_router)
api_v1.include_router(lines_router)
api_v1.include_router(system_router)
api_v1.include_router(rbac_router)
api_v1.include_router(users_router)
api_v1.include_router(presence_router)
api_v1.include_router(totp_router)
api_v1.include_router(telephony_router)
api_v1.include_router(workflows_router)
api_v1.include_router(technical_endpoints_router)
api_v1.include_router(trigger_rules_router)
api_v1.include_router(trigger_diagnostics_router)
api_v1.include_router(client_popups_router)
api_v1.include_router(coda_alarm_sources_router)
api_v1.include_router(integrations_router)
api_v1.include_router(door_action_profiles_router)


class MetaResponse(BaseModel):
    service: str
    version: str
    api_version: str
    environment: str
    node_id: str
    capabilities: list[str]
    known_integrations: list[str]


@api_v1.get("/meta", response_model=MetaResponse, tags=["meta"])
async def meta() -> MetaResponse:
    s = get_settings()
    return MetaResponse(
        service=s.service_name,
        version=__version__,
        api_version="v1",
        environment=s.environment,
        node_id=s.node_id,
        # Foundation phase: no business capabilities yet. Listed explicitly so
        # clients can feature-detect as Phase 1+ turns these on.
        capabilities=[],
        known_integrations=sorted(IntegrationRegistry.discover_manifest_ids()),
    )
