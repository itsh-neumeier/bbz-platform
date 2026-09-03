"""Admin: directory (LDAP/AD) connection test (#723, part of #718).

The LDAP connection fields are edited through the generic settings API
(`/admin/settings/directory`, group `directory`); the bind password stays with
the `SecretProvider` (ADR-0019). This endpoint runs a one-shot reachability /
TLS / service-bind / sample-search check against the **effective** config
(settings store → env) so an operator can verify it without a login attempt.
No directory data is returned — only booleans and a small count.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.auth.ldap import LdapClient
from bbz_core.auth.ldap.errors import LdapConfigError
from bbz_core.infra.repositories.ldap_login import config_from_store

router = APIRouter(prefix="/admin/directory", tags=["admin"])


class DirectoryTestOut(BaseModel):
    configured: bool
    reachable: bool = False
    tls_ok: bool = False
    bind_ok: bool = False
    #: number of accounts the enumeration filter matched (capped at 5)
    sample_count: int | None = None
    error: str | None = None


@router.post("/test", response_model=DirectoryTestOut)
async def test_directory(
    _: AuthContext = Depends(require("system.settings.manage")),
    session: AsyncSession = Depends(db_session),
) -> DirectoryTestOut:
    try:
        cfg = await config_from_store(session)
    except LdapConfigError as exc:
        return DirectoryTestOut(configured=False, error=str(exc))
    probe = await asyncio.to_thread(LdapClient(cfg).probe)
    return DirectoryTestOut(configured=True, **probe)
