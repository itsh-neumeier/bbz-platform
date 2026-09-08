"""Admin: SIP music-on-hold files (roadmap E13-12 / #817).

Upload / list / delete the WAV files that play while a call waits for an
operator or is on hold, then assign them per line
(``PUT /admin/telephony/sip/lines/{id}`` carries ``ring_moh_file_id`` /
``hold_moh_file_id``). The bytes live on disk under ``$BBZ_MOH_DIR``, not the
DB. Every route needs ``integrations.configure``. Upload / delete emit a
critical audit row; the bytes / sha are metadata, not secrets.

Upload is a **raw body** (``Content-Type: audio/wav`` + the WAV bytes) plus a
``?name=`` — BBZ carries no multipart parser and a single-file upload does not
need one.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.infra.moh_store import MAX_BYTES, MohFileError
from bbz_core.infra.repositories.sip_moh_config import (
    SipMohConfigService,
    SipMohError,
    SipMohFileView,
    SipMohInUseError,
    SipMohNotFoundError,
)

router = APIRouter(prefix="/admin/telephony/moh", tags=["admin"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except SipMohNotFoundError as exc:
        raise NotFoundError(str(exc) or "MoH file not found") from exc
    except SipMohInUseError as exc:
        raise ConflictError(str(exc)) from exc
    except (SipMohError, MohFileError) as exc:
        raise ValidationError(str(exc)) from exc


class MohFileOut(BaseModel):
    id: uuid.UUID
    name: str
    original_filename: str
    mime: str
    size_bytes: int
    sha256: str
    uploaded_at: _dt.datetime
    #: bbz_line_ids that use this file (empty → deletable)
    used_by: list[str]


class MohFilesOut(BaseModel):
    files: list[MohFileOut]


def _out(v: SipMohFileView) -> MohFileOut:
    return MohFileOut(
        id=v.id,
        name=v.name,
        original_filename=v.original_filename,
        mime=v.mime,
        size_bytes=v.size_bytes,
        sha256=v.sha256,
        uploaded_at=v.uploaded_at,
        used_by=v.used_by,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> SipMohConfigService:
    return SipMohConfigService(session)


@router.get("", response_model=MohFilesOut)
async def list_moh_files(
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipMohConfigService = Depends(_svc),
) -> MohFilesOut:
    return MohFilesOut(files=[_out(v) for v in await svc.list_files()])


@router.post("", response_model=MohFileOut)
async def upload_moh_file(
    request: Request,
    name: str = Query(default="", max_length=120),
    filename: str = Query(default="", max_length=255),
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipMohConfigService = Depends(_svc),
) -> MohFileOut:
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise ValidationError(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MiB")
    mime = request.headers.get("content-type", "").split(";", 1)[0].strip()
    with _translate():
        v = await svc.upload(
            name=name,
            original_filename=filename,
            mime=mime,
            data=data,
            actor_id=ctx.user_id,
        )
    return _out(v)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_moh_file(
    file_id: uuid.UUID,
    ctx: AuthContext = Depends(require("integrations.configure")),
    svc: SipMohConfigService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete_file(file_id, actor_id=ctx.user_id)


@router.get("/manifest")
async def moh_sync_manifest(
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipMohConfigService = Depends(_svc),
) -> Response:
    """``<id> <sha256>`` per referenced file, one per line — for
    ``sync-trunk-config.sh`` (no ``jq`` on the box). It downloads each via
    ``GET .../moh/{id}/download`` and drops it at ``<dir>/<id>/moh.wav``."""
    lines = "\n".join(f"{m['id']} {m['sha256']}" for m in await svc.sync_manifest())
    return Response(
        content=(lines + "\n") if lines else "",
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{file_id}/download")
async def download_moh_file(
    file_id: uuid.UUID,
    _: AuthContext = Depends(require("integrations.configure")),
    svc: SipMohConfigService = Depends(_svc),
) -> Response:
    with _translate():
        data, fname = await svc.read_bytes(file_id)
    return Response(
        content=data,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Cache-Control": "no-store",
        },
    )
