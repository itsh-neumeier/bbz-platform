"""Uniform error envelope.

Every error response has the same shape so clients (web, kiosk, agents) can
handle failures generically. Write-conflict handling (HTTP 409 with the current
server version, MASTER_PROMPT §15) gets its concrete payload in Phase 1; the
envelope and the exception type are defined here now.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Base class for all deliberately raised API errors."""

    code = "internal_error"
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ConflictError(AppError):
    """Optimistic-concurrency conflict. Phase 1 attaches the current version."""

    code = "conflict"
    http_status = status.HTTP_409_CONFLICT


class NotFoundError(AppError):
    code = "not_found"
    http_status = status.HTTP_404_NOT_FOUND


class UnauthorizedError(AppError):
    """No valid authentication was presented."""

    code = "unauthorized"
    http_status = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    """Authenticated, but not allowed (missing permission or CSRF token)."""

    code = "forbidden"
    http_status = status.HTTP_403_FORBIDDEN


class ValidationError(AppError):
    code = "validation_error"
    http_status = 422


class TotpRequiredError(AppError):
    """Password was correct but a valid TOTP / recovery code is required."""

    code = "totp_required"
    http_status = status.HTTP_401_UNAUTHORIZED


def _render(request: Request, exc: AppError) -> JSONResponse:
    from bbz_core.logging import correlation_id

    body = ErrorResponse(
        error=ErrorBody(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            correlation_id=correlation_id.get(),
        )
    )
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(request: Request, exc: AppError) -> JSONResponse:
        return _render(request, exc)
