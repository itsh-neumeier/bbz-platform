"""External identity-provider group → BBZ role mapping (roadmap E21-02).

``auth_group_mappings`` is admin-configured: "IdP group X grants BBZ role Y".
``external_role_assignments`` records which ``user_roles`` rows a mapping created,
so that reconciliation on the next login can drop a role the user lost *without*
ever touching a role an admin assigned by hand.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class AuthGroupMapping(Base, TimestampMixin):
    """One rule: for ``provider``, membership in ``external_group`` grants
    ``role_key``."""

    __tablename__ = "auth_group_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_group", "role_key", name="uq_auth_group_mappings_rule"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(64), index=True)
    #: the IdP group / role claim value (verbatim)
    external_group: Mapped[str] = mapped_column(String(300))
    #: ``roles.key`` this membership grants
    role_key: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ExternalRoleAssignment(Base):
    """A ``user_roles`` row that an :class:`AuthGroupMapping` produced. Removing
    the mapping-granted role on the next login deletes both rows; a manual grant
    (no row here) is left alone."""

    __tablename__ = "external_role_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    assigned_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
