"""Seed one user for the HA harness (roadmap E06-11).

Run inside an api container: ``docker compose exec -T api1 python /seed.py``.
Idempotent. Creates ``ha-probe`` / ``ha-probe-pw-32-bytes-minimum!!`` with the
permissions the scenario scripts need.
"""

from __future__ import annotations

import asyncio

_PERMS = ["events.create", "events.view", "system.cluster.view", "system.cluster.manage"]
_USER = "ha-probe"
_PASSWORD = "ha-probe-pw-32-bytes-minimum!!"  # harness only, not a real credential


async def _main() -> None:
    from sqlalchemy import select

    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    async with session_scope() as s, s.begin():
        if (
            await s.execute(select(AuthIdentity).where(AuthIdentity.subject == _USER))
        ).scalar_one_or_none():
            print("ha-probe already seeded")
            return
        u = User(display_name="HA Probe")
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject=_USER)
        s.add(ident)
        await s.flush()
        s.add(LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(_PASSWORD)))
        role = Role(key="r-ha-probe", name="HA probe")
        s.add(role)
        await s.flush()
        for key in _PERMS:
            pid = (
                await s.execute(select(Permission.id).where(Permission.key == key))
            ).scalar_one_or_none()
            if pid is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
                pid = p.id
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    print("ha-probe seeded")


if __name__ == "__main__":
    asyncio.run(_main())
