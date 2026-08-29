"""Schema-shape checks for the identity models (no live database).

Real upgrade/downgrade/upgrade against PostgreSQL runs in CI's backend job.
"""

from __future__ import annotations

from bbz_core.infra.models import AuthIdentity, Base, User, UserPresence


def test_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"users", "auth_identities", "user_presence"} <= tables


def test_auth_identity_unique_provider_subject() -> None:
    uqs = [
        tuple(c.name for c in con.columns)
        for con in AuthIdentity.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("provider", "subject") in uqs


def test_auth_identity_fk_cascades() -> None:
    fk = next(iter(AuthIdentity.__table__.foreign_keys))
    assert fk.column.table.name == "users"
    assert fk.ondelete == "CASCADE"


def test_presence_pk_is_user_id_and_cascades() -> None:
    assert [c.name for c in UserPresence.__table__.primary_key.columns] == ["user_id"]
    ondelete = {fk.parent.name: fk.ondelete for fk in UserPresence.__table__.foreign_keys}
    assert ondelete == {"user_id": "CASCADE", "changed_by": "SET NULL"}


def test_user_has_server_default_uuid_and_timestamps() -> None:
    cols = User.__table__.columns
    assert cols["id"].server_default is not None
    assert cols["created_at"].type.timezone is True  # type: ignore[attr-defined]
    assert cols["updated_at"].type.timezone is True  # type: ignore[attr-defined]
