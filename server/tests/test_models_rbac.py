"""Schema-shape checks for the RBAC models (no live database)."""

from __future__ import annotations

from bbz_core.infra.models import (
    Base,
    RolePermission,
    Scope,
    UserGroup,
    UserRole,
)


def test_rbac_tables_registered() -> None:
    assert {
        "permissions",
        "roles",
        "groups",
        "role_permissions",
        "user_roles",
        "group_roles",
        "user_groups",
    } <= set(Base.metadata.tables)


def test_role_permission_unique_triplet() -> None:
    uqs = [
        tuple(c.name for c in con.columns)
        for con in RolePermission.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("role_id", "permission_id", "scope") in uqs


def test_role_permission_scope_check_lists_all_scopes() -> None:
    checks = [
        str(con.sqltext)
        for con in RolePermission.__table__.constraints
        if con.__class__.__name__ == "CheckConstraint"
    ]
    assert checks and all(s.value in checks[0] for s in Scope)


def test_role_permission_condition_is_nullable_jsonb() -> None:
    col = RolePermission.__table__.columns["condition"]
    assert col.nullable is True
    assert col.type.__class__.__name__ == "JSONB"


def test_assignment_tables_have_composite_pk_and_cascade() -> None:
    for model, cols in ((UserRole, ("user_id", "role_id")), (UserGroup, ("user_id", "group_id"))):
        assert tuple(c.name for c in model.__table__.primary_key.columns) == cols
        cascades = {fk.parent.name: fk.ondelete for fk in model.__table__.foreign_keys}
        assert cascades[cols[0]] == "CASCADE" and cascades[cols[1]] == "CASCADE"
