"""Directory sync — reconcile BBZ users/roles against the directory (roadmap E21-04).

A leader-elected singleton (``directory-sync``) enumerates every account in the
directory and diffs it against the BBZ ``ldap_ad`` identities:

* **new** in the directory  → provision a BBZ user (if ``ldap_sync_provision``)
* **gone** from the directory → soft-deactivate the BBZ user (never a hard delete)
  and revoke its sessions — reliable off-boarding
* **present**                → refresh display name / email, reconcile the
  group-mapped roles via the shared :class:`GroupMappingService` (E21-02)

Safety: a run that returns **no** accounts, or that would deactivate more than
``ldap_sync_max_deactivations`` users, aborts and changes nothing — a directory
outage must never mass-off-board. ``dry_run`` computes the full diff and writes
**nothing** (no rows, no audit). Every real run audits ``DIRECTORY_SYNC_COMPLETED``
and one ``USER_DEACTIVATED`` per off-boarded account.

The blocking ``ldap3`` enumeration runs in a worker thread. The reconcile is not
one transaction — each user's change + its audit row commit together, mirroring
the OIDC/Weytec reconcile pattern.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.ldap import LdapClient, LdapError, LdapPrincipal
from bbz_core.infra.models.directory_sync import DirectorySyncState
from bbz_core.infra.models.identity import AuthIdentity, User, UserStatus
from bbz_core.infra.models.rbac import Role, UserRole
from bbz_core.infra.models.session import Session
from bbz_core.infra.repositories.auth_group_mapping import GroupMappingService
from bbz_core.infra.repositories.ldap_login import config_from_settings
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)
_PROVIDER = "ldap_ad"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


@dataclass
class DirectorySyncReport:
    source: str = _PROVIDER
    ok: bool = True
    dry_run: bool = False
    aborted: bool = False
    error: str | None = None
    scanned: int = 0
    created: int = 0
    deactivated: int = 0
    role_reconciles: int = 0
    profile_updates: int = 0
    errors: int = 0
    #: uids (dry-run: what *would* happen)
    created_uids: list[str] = field(default_factory=list)
    deactivated_uids: list[str] = field(default_factory=list)

    def as_summary(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "aborted": self.aborted,
            "error": self.error,
            "scanned": self.scanned,
            "created": self.created,
            "deactivated": self.deactivated,
            "role_reconciles": self.role_reconciles,
            "profile_updates": self.profile_updates,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class _BbzUser:
    user_id: uuid.UUID
    status: str
    display_name: str
    email: str | None


class DirectorySyncService:
    def __init__(self, session: AsyncSession, *, client: LdapClient | None = None) -> None:
        self._s = session
        self._client = client

    async def run(
        self, *, dry_run: bool = False, force: bool = False, actor_id: uuid.UUID | None = None
    ) -> DirectorySyncReport:
        """Enumerate the directory and reconcile. Never raises — a failure is
        recorded in ``directory_sync_state`` and returned in the report."""
        report = DirectorySyncReport(dry_run=dry_run)
        started = _now()

        try:
            client = self._client or LdapClient(config_from_settings())
            principals = await asyncio.to_thread(client.enumerate_principals)
        except LdapError as exc:
            return await self._fail(report, started, f"{type(exc).__name__}: {exc}", dry_run)

        report.scanned = len(principals)
        if not principals:
            return await self._fail(
                report, started, "directory returned no accounts (treated as an error)", dry_run
            )

        by_uid: dict[str, LdapPrincipal] = {p.uid: p for p in principals if p.uid}
        bbz = await self._load_bbz_users()

        new_uids = [u for u in by_uid if u not in bbz]
        vanished = [
            (uid, row.user_id)
            for uid, row in bbz.items()
            if uid not in by_uid and row.status == UserStatus.ACTIVE.value
        ]

        if not force and len(vanished) > get_settings().ldap_sync_max_deactivations:
            report.deactivated_uids = sorted(uid for uid, _ in vanished)
            return await self._fail(
                report,
                started,
                f"{len(vanished)} deactivations exceed the cap "
                f"({get_settings().ldap_sync_max_deactivations}); rerun with force to override",
                dry_run,
                aborted=True,
            )

        if dry_run:
            report.created_uids = sorted(new_uids)
            report.deactivated_uids = sorted(uid for uid, _ in vanished)
            report.created = len(new_uids)
            report.deactivated = len(vanished)
            return report  # dry run writes nothing

        provisioned = await self._provision(new_uids, by_uid, report)
        await self._deactivate(vanished, actor_id, report)

        # groups + profile for every present, active user (including the new ones)
        active_ids: dict[str, uuid.UUID] = {**provisioned}
        for uid, row in bbz.items():
            if uid in by_uid and row.status == UserStatus.ACTIVE.value:
                active_ids[uid] = row.user_id
        await self._reconcile_present(active_ids, by_uid, bbz, report)

        await self._succeed(report, started, actor_id)
        return report

    # --- steps ------------------------------------------------------------

    async def _load_bbz_users(self) -> dict[str, _BbzUser]:
        await self._s.rollback()
        rows = (
            await self._s.execute(
                select(AuthIdentity.subject, User.id, User.status, User.display_name)
                .join(User, User.id == AuthIdentity.user_id)
                .where(AuthIdentity.provider == _PROVIDER)
            )
        ).all()
        out: dict[str, _BbzUser] = {}
        for subject, user_id, status, display_name in rows:
            out[subject] = _BbzUser(
                user_id=user_id, status=status, display_name=display_name, email=None
            )
        return out

    async def _provision(
        self,
        new_uids: list[str],
        by_uid: dict[str, LdapPrincipal],
        report: DirectorySyncReport,
    ) -> dict[str, uuid.UUID]:
        if not new_uids or not get_settings().ldap_sync_provision:
            return {}
        default_role = get_settings().oidc_jit_default_role.strip()
        created: dict[str, uuid.UUID] = {}
        await self._s.rollback()
        async with self._s.begin():
            role_id = None
            if default_role:
                role_id = (
                    await self._s.execute(select(Role.id).where(Role.key == default_role))
                ).scalar_one_or_none()
            for uid in new_uids:
                p = by_uid[uid]
                user = User(display_name=p.display_name or p.email or uid)
                self._s.add(user)
                await self._s.flush()
                self._s.add(AuthIdentity(user_id=user.id, provider=_PROVIDER, subject=uid))
                if role_id is not None:
                    self._s.add(UserRole(user_id=user.id, role_id=role_id, granted_by=None))
                created[uid] = user.id
        report.created = len(created)
        report.created_uids = sorted(created)
        return created

    async def _deactivate(
        self,
        vanished: list[tuple[str, uuid.UUID]],
        actor_id: uuid.UUID | None,
        report: DirectorySyncReport,
    ) -> None:
        for uid, user_id in vanished:
            try:
                await self._s.rollback()
                async with self._s.begin():
                    await self._s.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(status=UserStatus.DISABLED.value)
                    )
                    await self._s.execute(
                        update(Session)
                        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
                        .values(revoked_at=_now())
                    )
                    await AuditService(self._s).write(
                        AuditAction.USER_DEACTIVATED,
                        actor_user_id=actor_id,
                        target_type="user",
                        target_id=str(user_id),
                        before={"status": UserStatus.ACTIVE.value},
                        after={"status": UserStatus.DISABLED.value},
                        reason=f"directory sync: {_PROVIDER} account '{uid}' no longer present",
                    )
                report.deactivated += 1
                report.deactivated_uids.append(uid)
            except Exception as exc:  # one bad user must not stop the run
                _log.warning("directory_sync_deactivate_failed", uid=uid, error=repr(exc))
                report.errors += 1

    async def _reconcile_present(
        self,
        active_ids: dict[str, uuid.UUID],
        by_uid: dict[str, LdapPrincipal],
        bbz: dict[str, _BbzUser],
        report: DirectorySyncReport,
    ) -> None:
        mapper = GroupMappingService(self._s)
        for uid, user_id in active_ids.items():
            p = by_uid[uid]
            try:
                existing = bbz.get(uid)
                if existing is not None:
                    await self._refresh_profile(user_id, p, existing, report)
                await mapper.sync_user_roles(
                    user_id=user_id, provider=_PROVIDER, external_groups=p.groups
                )
                report.role_reconciles += 1
            except Exception as exc:  # keep going for the rest of the directory
                _log.warning("directory_sync_reconcile_failed", uid=uid, error=repr(exc))
                report.errors += 1

    async def _refresh_profile(
        self,
        user_id: uuid.UUID,
        principal: LdapPrincipal,
        existing: _BbzUser,
        report: DirectorySyncReport,
    ) -> None:
        want_name = principal.display_name or existing.display_name
        if want_name == existing.display_name:
            return
        await self._s.rollback()
        async with self._s.begin():
            await self._s.execute(
                update(User).where(User.id == user_id).values(display_name=want_name)
            )
        report.profile_updates += 1

    # --- state + audit --------------------------------------------------

    async def _succeed(
        self, report: DirectorySyncReport, started: _dt.datetime, actor_id: uuid.UUID | None
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await AuditService(self._s).write(
                AuditAction.DIRECTORY_SYNC_COMPLETED,
                actor_user_id=actor_id,
                target_type="directory_source",
                target_id=_PROVIDER,
                after=report.as_summary(),
            )
            await self._store_state(started, report, ok=True)

    async def _fail(
        self,
        report: DirectorySyncReport,
        started: _dt.datetime,
        message: str,
        dry_run: bool,
        *,
        aborted: bool = False,
    ) -> DirectorySyncReport:
        report.ok = False
        report.aborted = aborted
        report.error = message
        _log.warning("directory_sync_failed", error=message, aborted=aborted)
        if not dry_run:
            await self._s.rollback()
            async with self._s.begin():
                await self._store_state(started, report, ok=False)
        return report

    async def _store_state(
        self, started: _dt.datetime, report: DirectorySyncReport, *, ok: bool
    ) -> None:
        values = {
            "source": _PROVIDER,
            "last_run_at": started,
            "last_error": None if ok else report.error,
            "last_summary": report.as_summary(),
            "updated_at": started,
        }
        set_ = {k: v for k, v in values.items() if k != "source"}
        if ok:
            values["last_success_at"] = started
            set_["last_success_at"] = started
        await self._s.execute(
            pg_insert(DirectorySyncState)
            .values(**values)
            .on_conflict_do_update(index_elements=["source"], set_=set_)
        )
