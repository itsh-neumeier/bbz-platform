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
from bbz_core.api.v1.router import api_v1
from bbz_core.api.ws import router as ws_router
from bbz_core.infra.db import dispose_engine
from bbz_core.logging import configure_logging, correlation_id, get_logger
from bbz_core.settings import get_settings
from bbz_core.telemetry import instrument_app

_log = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["x-correlation-id"] = cid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(level=s.log_level, json=s.log_json)
    _log.info("startup", service=s.service_name, version=__version__, environment=s.environment)
    yield
    await dispose_engine()
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

    instrument_app(app)
    return app


app = create_app()
