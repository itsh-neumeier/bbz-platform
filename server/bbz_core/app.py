"""FastAPI application factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from bbz_core import __version__
from bbz_core.api.cluster import router as cluster_router
from bbz_core.api.errors import install_error_handlers
from bbz_core.api.health import router as health_router
from bbz_core.api.request_metrics import RequestMetricsMiddleware
from bbz_core.api.v1.router import api_v1
from bbz_core.api.ws import router as ws_router
from bbz_core.infra.db import dispose_engine
from bbz_core.logging import configure_logging, correlation_id, get_logger, user_id
from bbz_core.secrets import verify_required_secrets
from bbz_core.settings import get_settings
from bbz_core.telemetry import instrument_app, record_correlation_id, shutdown_tracing
from bbz_core.workers.manager import ClusterWorkers

_log = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        token = correlation_id.set(cid)
        uid_token = user_id.set(None)  # cleared per request; current_auth fills it (E22-03)
        record_correlation_id(cid)  # -> bbz.correlation_id span attribute (E22-01)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
            user_id.reset(uid_token)
        response.headers["x-correlation-id"] = cid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(
        level=s.log_level,
        json=s.log_json,
        node_id=s.node_id,
        module_levels=s.log_levels,
        sample=s.log_sample,
        log_file=s.log_file,
    )
    verify_required_secrets(s)  # fail-closed: refuse to start on a broken prod secret (E23-01)
    _log.info("startup", service=s.service_name, version=__version__, environment=s.environment)

    workers: ClusterWorkers | None = None
    if s.run_background_workers:
        workers = ClusterWorkers()
        await workers.start()
    try:
        yield
    finally:
        if workers is not None:
            await workers.stop()
        await dispose_engine()
        shutdown_tracing()
        _log.info("shutdown")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="BBZ Platform Core API",
        version=__version__,
        summary="BBZ / 3-S-Zentrale platform core service. Foundation phase.",
        root_path=s.api_root_path,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestMetricsMiddleware)  # times requests (E22-02)
    if s.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(cluster_router)
    app.include_router(ws_router)
    app.include_router(api_v1)

    # normalized telephony events → call aggregate (E11-04)
    from bbz_core.infra.repositories.call_lifecycle import register_call_dispatch

    register_call_dispatch()

    instrument_app(app)
    return app


app = create_app()
