"""SIP music-on-hold: filespace + config generation (E13-12 / #817).

Bytes land on disk (never the DB), only a real WAV is accepted, a file in use
by a line cannot be deleted, and the generated musiconhold.conf has one class
per referenced file.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra import moh_store
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.sip_gateway import SipMohFile
from bbz_core.infra.repositories.sip_config import SipConfigError, SipConfigService
from bbz_core.infra.repositories.sip_moh_config import (
    SipMohConfigService,
    SipMohInUseError,
    SipMohNotFoundError,
)


def _wav(payload: bytes = b"\x00" * 32) -> bytes:
    """A minimal-but-real 8 kHz mono 8-bit RIFF/WAVE container."""
    body = (
        b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (8000).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (8).to_bytes(2, "little")
        + b"data"
        + len(payload).to_bytes(4, "little")
        + payload
    )
    return b"RIFF" + (len(body)).to_bytes(4, "little") + body


@pytest.fixture(autouse=True)
def _moh_dir(tmp_path: Path) -> Iterator[None]:
    import bbz_core.settings as settings_mod

    os.environ["BBZ_MOH_DIR"] = str(tmp_path / "moh")
    os.environ["BBZ_MOH_ASTERISK_DIR"] = "/var/lib/asterisk/moh/bbz"
    settings_mod.get_settings.cache_clear()
    yield
    for k in ("BBZ_MOH_DIR", "BBZ_MOH_ASTERISK_DIR"):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def svc(db: AsyncSession) -> AsyncIterator[SipMohConfigService]:
    yield SipMohConfigService(db)


async def test_wav_validation() -> None:
    moh_store.validate_wav(_wav(), mime="audio/wav")
    with pytest.raises(moh_store.MohFileError):
        moh_store.validate_wav(b"not a wav at all", mime="audio/wav")
    with pytest.raises(moh_store.MohFileError):
        moh_store.validate_wav(_wav(), mime="audio/mpeg")
    with pytest.raises(moh_store.MohFileError):
        moh_store.validate_wav(b"", mime="audio/wav")
    with pytest.raises(moh_store.MohFileError):
        moh_store.validate_wav(b"RIFF" + b"\x00" * (11 * 1024 * 1024) + b"WAVE", mime="audio/wav")


async def test_upload_writes_bytes_to_disk_not_the_db(
    svc: SipMohConfigService, db: AsyncSession
) -> None:
    v = await svc.upload(
        name="Bahnhofsansage",
        original_filename="ansage.wav",
        mime="audio/wav",
        data=_wav(b"\x10" * 64),
        actor_id=None,
    )
    assert v.name == "Bahnhofsansage" and v.size_bytes == len(_wav(b"\x10" * 64))
    assert v.sha256 and v.used_by == []

    row = await db.get(SipMohFile, v.id)
    assert row is not None
    assert not hasattr(row, "data") and not hasattr(row, "bytes")  # metadata only
    assert moh_store.exists(v.id)
    data, fname = await svc.read_bytes(v.id)
    assert data == _wav(b"\x10" * 64) and fname == "ansage.wav"

    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_MOH_UPLOADED" for r in rows)


async def test_a_bad_upload_is_rejected(svc: SipMohConfigService) -> None:
    with pytest.raises(moh_store.MohFileError):
        await svc.upload(
            name="x", original_filename="x.mp3", mime="audio/mpeg", data=b"junk", actor_id=None
        )


async def _line(db: AsyncSession, bbz_line_id: str, **moh: str | None) -> None:
    await SipConfigService(db).set_line(
        bbz_line_id,
        asterisk_endpoint=None,
        label="",
        enabled=True,
        actor_id=None,
        **moh,  # type: ignore[arg-type]
    )


async def test_delete_is_blocked_while_a_line_uses_the_file(
    svc: SipMohConfigService, db: AsyncSession
) -> None:
    v = await svc.upload(
        name="Halten", original_filename="h.wav", mime="audio/wav", data=_wav(), actor_id=None
    )
    await _line(db, "leonet-8870", hold_moh_file_id=str(v.id))

    with pytest.raises(SipMohInUseError):
        await svc.delete_file(v.id, actor_id=None)

    # reassign the line, then it deletes
    await _line(db, "leonet-8870", hold_moh_file_id=None)
    await svc.delete_file(v.id, actor_id=None)
    assert not moh_store.exists(v.id)
    with pytest.raises(SipMohNotFoundError):
        await svc.delete_file(v.id, actor_id=None)


async def test_set_line_rejects_an_unknown_moh_id(db: AsyncSession) -> None:
    with pytest.raises(SipConfigError):
        await _line(db, "l1", ring_moh_file_id=str(uuid.uuid4()))
    with pytest.raises(SipConfigError):
        await _line(db, "l1", ring_moh_file_id="not-a-uuid")


async def test_render_musiconhold_and_line_moh_map(
    svc: SipMohConfigService, db: AsyncSession
) -> None:
    ring = await svc.upload(
        name="Warte", original_filename="w.wav", mime="audio/wav", data=_wav(), actor_id=None
    )
    hold = await svc.upload(
        name="Halte", original_filename="h.wav", mime="audio/wav", data=_wav(b"\x22"), actor_id=None
    )
    await _line(db, "leonet-8870", ring_moh_file_id=str(ring.id), hold_moh_file_id=str(hold.id))
    await _line(db, "leonet-other", hold_moh_file_id=str(hold.id))

    conf = await svc.render_musiconhold()
    assert f"[bbz-moh-{ring.id}]" in conf
    assert f"[bbz-moh-{hold.id}]" in conf
    assert f"directory = /var/lib/asterisk/moh/bbz/{ring.id}" in conf
    assert "mode = files" in conf

    m = await svc.line_moh_map()
    assert m["leonet-8870"] == {"ring": f"bbz-moh-{ring.id}", "hold": f"bbz-moh-{hold.id}"}
    assert m["leonet-other"] == {"hold": f"bbz-moh-{hold.id}"}

    manifest = await svc.sync_manifest()
    assert {row["id"] for row in manifest} == {str(ring.id), str(hold.id)}

    # a file used by two lines still lists both
    listed = {v.id: v.used_by for v in await svc.list_files()}
    assert sorted(listed[hold.id]) == ["leonet-8870", "leonet-other"]


async def test_runtime_config_carries_line_moh(svc: SipMohConfigService, db: AsyncSession) -> None:
    cfg = SipConfigService(db)
    await cfg.set(
        host="pbx.local",
        port=8088,
        tls=False,
        app_name="bbz-sip",
        dtmf_transport="rfc2833",
        ari_username="u",
        ari_password=None,  # no encryption key in this test — MoH doesn't need one
        enabled=True,
        actor_id=None,
    )
    ring = await svc.upload(
        name="W", original_filename="w.wav", mime="audio/wav", data=_wav(), actor_id=None
    )
    await _line(db, "leonet-8870", ring_moh_file_id=str(ring.id))

    rc = await cfg.runtime_config()
    assert rc is not None
    assert rc["line_moh"] == {"leonet-8870": {"ring": f"bbz-moh-{ring.id}"}}
