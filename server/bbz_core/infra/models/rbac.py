"""RBAC tables: permissions, roles, groups and their assignments.

MASTER_PROMPT §12, roadmap E02-02. Fully dynamic model - roles/permissions are
data, not code. Schema only; the permission-check service (E02-06), scope
resolver (E02-07) and admin API (E02-09) come later.

A ``role_permissions`` row may carry a ``scope`` and an optional structured
``condition`` (Rule-DSL JSON, ADR-0010) - never executable code.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class Scope(enum.StrEnum):
    GLOBAL = "global"
    REGION = "region"
    BBZ = "bbz"
    WORKPLACE = "workplace"
    OWN_EVENTS = "own_events"
    ASSIGNED_EVENTS = "assigned_events"


_SCOPE_CHECK = CheckConstraint(
    "scope IN (" + ", ".join(f"'{s.value}'" for s in Scope) + ")",
    name="scope",
)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    area: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(255))


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # Builtin roles (E02-14 seed) may be re-permissioned but not deleted.
    builtin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", "scope"),
        _SCOPE_CHECK,
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(16), server_default=Scope.GLOBAL.value)
    # Structured Rule-DSL expression ({"op": ..., "args": [...]}). NULL = always.
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    granted_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class GroupRole(Base):
    __tablename__ = "group_roles"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
