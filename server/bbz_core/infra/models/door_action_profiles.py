"""Door-open action profiles (roadmap E17-02).

A named door-open action: the **encrypted** DTMF code plus its timing. The code
is a secret (MASTER_PROMPT §30 / .ai/SECURITY.md) — it is stored only as
``dtmf_ciphertext`` (Fernet, key in the secret store) and is never returned by
any API, logged, or put in an audit / event payload. The audit references this
row's id and name; a ``technical_endpoint`` points at it by ``dtmf_profile_id``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class DoorActionProfile(Base, TimestampMixin):
    __tablename__ = "door_action_profiles"
    __table_args__ = (
        CheckConstraint("post_dtmf_delay_ms >= 0 AND post_dtmf_delay_ms <= 10000", name="delay"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    #: Fernet ciphertext of the DTMF code — opaque without the key
    dtmf_ciphertext: Mapped[str] = mapped_column(Text)
    #: how long to wait after the DTMF before hanging up
    post_dtmf_delay_ms: Mapped[int] = mapped_column(Integer, server_default=text("500"))
    #: hang the call up automatically once the sequence + delay are done
    auto_hangup: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
