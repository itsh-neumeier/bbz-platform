from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core import __version__
from bbz_core.api.deps import db_session
from bbz_core.api.v1.account_linking import router as account_linking_router
from bbz_core.api.v1.admin_directory import router as admin_directory_router
from bbz_core.api.v1.admin_settings import router as admin_settings_router
from bbz_core.api.v1.audit import router as audit_router
from bbz_core.api.v1.auth import router as auth_router
from bbz_core.api.v1.auth_mappings import router as auth_mappings_router
from bbz_core.api.v1.calls import router as calls_router
from bbz_core.api.v1.client_popups import router as client_popups_router
from bbz_core.api.v1.coda_alarm_sources import router as coda_alarm_sources_router
from bbz_core.api.v1.contacts import router as contacts_router
from bbz_core.api.v1.delegations import router as delegations_router
from bbz_core.api.v1.directory_sync import router as directory_sync_router
from bbz_core.api.v1.door_action_profiles import router as door_action_profiles_router
from bbz_core.api.v1.doors import router as doors_router
from bbz_core.api.v1.events import router as events_router
from bbz_core.api.v1.integrations import router as integrations_router
from bbz_core.api.v1.lines import router as lines_router
from bbz_core.api.v1.mfa_policies import router as mfa_policies_router
from bbz_core.api.v1.monitor import router as monitor_router
from bbz_core.api.v1.presence import router as presence_router
from bbz_core.api.v1.rbac import router as rbac_router
from bbz_core.api.v1.system import router as system_router
from bbz_core.api.v1.technical_endpoints import router as technical_endpoints_router
from bbz_core.api.v1.telephony import router as telephony_router
from bbz_core.api.v1.totp import router as totp_router
from bbz_core.api.v1.trigger_diagnostics import router as trigger_diagnostics_router
from bbz_core.api.v1.trigger_rules import router as trigger_rules_router
from bbz_core.api.v1.users import router as users_router
from bbz_core.api.v1.weather import router as weather_router
from bbz_core.api.v1.webauthn import router as webauthn_router
from bbz_core.api.v1.workflows import router as workflows_router
from bbz_core.infra.repositories.settings_store import SettingsStore
from bbz_core.integrations_host.registry import IntegrationRegistry
from bbz_core.settings import get_settings
from bbz_core.settings_catalog import SPEC_BY_KEY

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
api_v1.include_router(account_linking_router)
api_v1.include_router(auth_mappings_router)
api_v1.include_router(directory_sync_router)
api_v1.include_router(mfa_policies_router)
api_v1.include_router(audit_router)
api_v1.include_router(events_router)
api_v1.include_router(calls_router)
api_v1.include_router(contacts_router)
api_v1.include_router(lines_router)
api_v1.include_router(system_router)
api_v1.include_router(rbac_router)
api_v1.include_router(delegations_router)
api_v1.include_router(users_router)
api_v1.include_router(presence_router)
api_v1.include_router(totp_router)
api_v1.include_router(webauthn_router)
api_v1.include_router(telephony_router)
api_v1.include_router(workflows_router)
api_v1.include_router(technical_endpoints_router)
api_v1.include_router(trigger_rules_router)
api_v1.include_router(trigger_diagnostics_router)
api_v1.include_router(client_popups_router)
api_v1.include_router(coda_alarm_sources_router)
api_v1.include_router(integrations_router)
api_v1.include_router(door_action_profiles_router)
api_v1.include_router(doors_router)
api_v1.include_router(weather_router)
api_v1.include_router(monitor_router)
api_v1.include_router(admin_settings_router)
api_v1.include_router(admin_directory_router)


class MetaResponse(BaseModel):
    service: str
    version: str
    api_version: str
    environment: str
    node_id: str
    #: operator-facing name of this BBZ instance (runtime setting, ADR-0031) —
    #: e.g. "BBZ Nürnberg". Public so the login screen can show it.
    instance_name: str
    instance_short_name: str
    capabilities: list[str]
    known_integrations: list[str]


@api_v1.get("/meta", response_model=MetaResponse, tags=["meta"])
async def meta(session: AsyncSession = Depends(db_session)) -> MetaResponse:
    s = get_settings()
    store = SettingsStore(session)
    try:
        instance_name = str(await store.effective("instance.name"))
        instance_short_name = str(await store.effective("instance.short_name"))
    except (SQLAlchemyError, OSError):
        # /meta is the pre-login bootstrap call — a DB blip must not 500 it.
        instance_name = str(SPEC_BY_KEY["instance.name"].default)
        instance_short_name = str(SPEC_BY_KEY["instance.short_name"].default)
    return MetaResponse(
        service=s.service_name,
        version=__version__,
        api_version="v1",
        environment=s.environment,
        node_id=s.node_id,
        instance_name=instance_name,
        instance_short_name=instance_short_name,
        # Foundation phase: no business capabilities yet. Listed explicitly so
        # clients can feature-detect as Phase 1+ turns these on.
        capabilities=[],
        known_integrations=sorted(IntegrationRegistry.discover_manifest_ids()),
    )
