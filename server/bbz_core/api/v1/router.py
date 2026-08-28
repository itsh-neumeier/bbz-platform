from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from bbz_core import __version__
from bbz_core.integrations_host.registry import IntegrationRegistry
from bbz_core.settings import get_settings

api_v1 = APIRouter(prefix="/api/v1", tags=["meta"])


class MetaResponse(BaseModel):
    service: str
    version: str
    api_version: str
    environment: str
    node_id: str
    capabilities: list[str]
    known_integrations: list[str]


@api_v1.get("/meta", response_model=MetaResponse)
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
