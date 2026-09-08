"""On-disk store for the SIP music-on-hold WAV files (E13-12 / #817).

The DB row (``sip_moh_files``) is metadata only; the bytes live under
``$BBZ_MOH_DIR`` (default ``/var/lib/bbz/moh``), one file per row named by its
UUID. Asterisk's ``musiconhold.conf`` classes point at
``<dir>/<id>/`` — the sync script rsyncs the tree onto the box.

Validation is deliberately narrow: a real RIFF/WAVE container, ``<= 10 MiB``.
Format transcoding (Asterisk likes 8 kHz/16-bit mono) is a documented follow-up,
not done here.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from bbz_core.settings import get_settings

MAX_BYTES = 10 * 1024 * 1024
_WAV_MIMES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})


class MohFileError(ValueError):
    """The upload is not an acceptable WAV."""


def moh_dir() -> Path:
    return Path(get_settings().moh_dir)


def _looks_like_wav(data: bytes) -> bool:
    # RIFF <size> WAVE — the minimal canonical WAV header
    return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"


def validate_wav(data: bytes, *, mime: str) -> None:
    if not data:
        raise MohFileError("the upload is empty")
    if len(data) > MAX_BYTES:
        raise MohFileError(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MiB")
    if mime and mime.lower() not in _WAV_MIMES:
        raise MohFileError(f"unsupported content type {mime!r} — upload a WAV file")
    if not _looks_like_wav(data):
        raise MohFileError("not a WAV file (no RIFF/WAVE header)")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slot(file_id: uuid.UUID) -> Path:
    """``<dir>/<id>/moh.wav`` — a per-file directory so a musiconhold.conf class
    can be ``directory=<dir>/<id>`` (Asterisk plays every file in the dir)."""
    return moh_dir() / str(file_id) / "moh.wav"


def write(file_id: uuid.UUID, data: bytes) -> None:
    slot = _slot(file_id)
    slot.parent.mkdir(parents=True, exist_ok=True)
    tmp = slot.with_suffix(".wav.tmp")
    tmp.write_bytes(data)
    tmp.replace(slot)


def read(file_id: uuid.UUID) -> bytes:
    try:
        return _slot(file_id).read_bytes()
    except OSError as exc:
        raise MohFileError(f"MoH file {file_id} is not on disk") from exc


def exists(file_id: uuid.UUID) -> bool:
    return _slot(file_id).is_file()


def delete(file_id: uuid.UUID) -> None:
    shutil.rmtree(moh_dir() / str(file_id), ignore_errors=True)
