"""SIP music-on-hold files + ``musiconhold.conf`` generation (E13-12 / #817).

Upload / list / delete the WAV files that play while a call waits for an
operator (``ring``) or is on hold (``hold``); a ``sip_lines`` row points at one
of each. The bytes live on disk (:mod:`bbz_core.infra.moh_store`), never the DB.
:meth:`SipMohConfigService.render_musiconhold` emits one class per referenced
file for the sync script; :meth:`line_moh_map` feeds the adapter.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra import moh_store
from bbz_core.infra.models.sip_gateway import SipLine, SipMohFile
from bbz_core.settings import get_settings


class SipMohError(ValueError):
    """A MoH operation is not allowed (bad file, or still in use)."""


class SipMohNotFoundError(SipMohError):
    pass


class SipMohInUseError(SipMohError):
    """The file is still assigned to a line — reassign the line first."""


@dataclass(frozen=True)
class SipMohFileView:
    id: uuid.UUID
    name: str
    original_filename: str
    mime: str
    size_bytes: int
    sha256: str
    uploaded_at: _dt.datetime
    #: lines that currently use this file (as ring and/or hold music)
    used_by: list[str]


def moh_class(file_id: uuid.UUID) -> str:
    return f"bbz-moh-{file_id}"


class SipMohConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_files(self) -> list[SipMohFileView]:
        rows = (await self._s.execute(select(SipMohFile).order_by(SipMohFile.name))).scalars().all()
        lines = (await self._s.execute(select(SipLine))).scalars().all()
        used: dict[uuid.UUID, list[str]] = {}
        for line in lines:
            for fid in (line.ring_moh_file_id, line.hold_moh_file_id):
                if fid is not None:
                    used.setdefault(fid, []).append(line.bbz_line_id)
        return [
            SipMohFileView(
                id=r.id,
                name=r.name,
                original_filename=r.original_filename,
                mime=r.mime,
                size_bytes=r.size_bytes,
                sha256=r.sha256,
                uploaded_at=r.uploaded_at,
                used_by=sorted(set(used.get(r.id, []))),
            )
            for r in rows
        ]

    async def upload(
        self,
        *,
        name: str,
        original_filename: str,
        mime: str,
        data: bytes,
        actor_id: uuid.UUID | None,
    ) -> SipMohFileView:
        display = name.strip() or original_filename.strip() or "Musik"
        moh_store.validate_wav(data, mime=mime)
        digest = moh_store.sha256_hex(data)

        await self._s.rollback()
        row = SipMohFile(
            id=uuid.uuid4(),
            name=display[:120],
            original_filename=original_filename.strip()[:255],
            mime=(mime or "audio/wav")[:64],
            size_bytes=len(data),
            sha256=digest,
            uploaded_by=actor_id,
        )
        self._s.add(row)
        await self._s.flush()
        moh_store.write(row.id, data)
        await AuditService(self._s).write(
            AuditAction.SIP_MOH_UPLOADED,
            actor_user_id=actor_id,
            target_type="sip_moh_file",
            target_id=str(row.id),
            after={
                "name": row.name,
                "original_filename": row.original_filename,
                "size_bytes": row.size_bytes,
                "sha256": row.sha256,
            },
        )
        await self._s.commit()
        return next(v for v in await self.list_files() if v.id == row.id)

    async def delete_file(self, file_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        row = await self._s.get(SipMohFile, file_id)
        if row is None:
            raise SipMohNotFoundError(str(file_id))
        in_use = (
            (
                await self._s.execute(
                    select(SipLine.bbz_line_id).where(
                        or_(
                            SipLine.ring_moh_file_id == file_id,
                            SipLine.hold_moh_file_id == file_id,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        if in_use:
            raise SipMohInUseError(f"still assigned to line(s): {', '.join(sorted(in_use))}")
        await AuditService(self._s).write(
            AuditAction.SIP_MOH_REMOVED,
            actor_user_id=actor_id,
            target_type="sip_moh_file",
            target_id=str(file_id),
            before={"name": row.name, "sha256": row.sha256},
        )
        await self._s.execute(delete(SipMohFile).where(SipMohFile.id == file_id))
        await self._s.commit()
        moh_store.delete(file_id)

    async def read_bytes(self, file_id: uuid.UUID) -> tuple[bytes, str]:
        row = await self._s.get(SipMohFile, file_id)
        if row is None:
            raise SipMohNotFoundError(str(file_id))
        return moh_store.read(file_id), row.original_filename or f"{file_id}.wav"

    # --- config generation ------------------------------------------

    async def _referenced_ids(self) -> list[uuid.UUID]:
        lines = (await self._s.execute(select(SipLine))).scalars().all()
        ids: set[uuid.UUID] = set()
        for line in lines:
            for fid in (line.ring_moh_file_id, line.hold_moh_file_id):
                if fid is not None:
                    ids.add(fid)
        return sorted(ids, key=str)

    async def render_musiconhold(self) -> str:
        """One ``[bbz-moh-<id>]`` class per file a line references. ``directory``
        is where the sync script drops the WAV tree on the Asterisk box."""
        ids = await self._referenced_ids()
        base = get_settings().moh_asterisk_dir.rstrip("/")
        out = [
            "; ==========================================================================",
            "; BBZ — generated music-on-hold classes (E13-12). DO NOT EDIT.",
            "; Overwritten by the BBZ sync script. #tryinclude from musiconhold.conf.",
            "; ==========================================================================",
        ]
        for fid in ids:
            out += [
                "",
                f"[{moh_class(fid)}]",
                "mode = files",
                f"directory = {base}/{fid}",
                "sort = alpha",
            ]
        return "\n".join(out).rstrip() + "\n"

    async def line_moh_map(self) -> dict[str, dict[str, str]]:
        """``{bbz_line_id: {"ring": "bbz-moh-<id>", "hold": "bbz-moh-<id>"}}`` —
        only the keys a line actually sets. The adapter starts the ``ring`` class
        on an unanswered inbound channel and uses ``hold`` on ``hold()``."""
        lines = (await self._s.execute(select(SipLine))).scalars().all()
        out: dict[str, dict[str, str]] = {}
        for line in lines:
            entry: dict[str, str] = {}
            if line.ring_moh_file_id is not None:
                entry["ring"] = moh_class(line.ring_moh_file_id)
            if line.hold_moh_file_id is not None:
                entry["hold"] = moh_class(line.hold_moh_file_id)
            if entry:
                out[line.bbz_line_id] = entry
        return out

    async def sync_manifest(self) -> list[dict[str, str]]:
        """``[{id, sha256, filename}]`` for every referenced file — the sync
        script downloads each and drops it at ``<dir>/<id>/moh.wav``."""
        ids = await self._referenced_ids()
        rows = {r.id: r for r in (await self._s.execute(select(SipMohFile))).scalars().all()}
        return [
            {"id": str(fid), "sha256": rows[fid].sha256, "filename": "moh.wav"}
            for fid in ids
            if fid in rows
        ]
