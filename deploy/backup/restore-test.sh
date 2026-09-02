#!/usr/bin/env sh
# Automated restore test (roadmap E24-05). Runs weekly on the backup host and
# proves the newest backups are actually restorable — a backup you have never
# restored is a hope, not a backup.
#
# It restores into a THROWAWAY location, checks integrity, tears it down, then
# POSTs the outcome to the API (`RESTORE_TEST_COMPLETED` audit +
# `bbz_restore_test_age_seconds` / `_ok` metrics; a `BbzRestoreTestStale` /
# `BbzRestoreTestFailing` alert watches them). Non-zero exit on any failure, so
# the systemd unit's `OnFailure=` fires.
#
#   GPG_RECIPIENT=<key> API=https://bbz.example.internal TOKEN=<bearer> \
#     ./restore-test.sh
#
# DRY_RUN=1 skips the API call (used by the test suite / a first manual run).
set -eu
. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

API="${API:-}"
TOKEN="${TOKEN:-}"
SCRATCH="${SCRATCH:-$(mktemp -d "${TMPDIR:-/tmp}/bbz-restore-test.XXXXXX")}"
PG_BIN="${PG_BIN:-/usr/lib/postgresql/16/bin}"
started=$(date -u +%s)
checked=""
ok=1
detail=""

cleanup() {
  [ -n "${PG_PID:-}" ] && kill "$PG_PID" 2>/dev/null || true
  rm -rf "$SCRATCH"
}
trap cleanup EXIT
fail() { ok=0; detail="${detail}${detail:+; }$1"; log "FAIL: $1"; }

# --- PostgreSQL: restore the newest base backup, start it, check it ----------
newest_pg=$(ls -1t "$BACKUP_DIR/postgres"/base-*.tar.gz.gpg 2>/dev/null | head -1 || true)
if [ -z "$newest_pg" ]; then
  fail "no PostgreSQL base backup found in $BACKUP_DIR/postgres"
else
  log "restoring $newest_pg"
  mkdir -p "$SCRATCH/pgdata"
  chmod 700 "$SCRATCH/pgdata"
  if gpg_decrypt "$newest_pg" | tar -xzf - -C "$SCRATCH/pgdata"; then
    "$PG_BIN/pg_ctl" -D "$SCRATCH/pgdata" -o "-p 55432 -k '' -c listen_addresses=''" \
      -l "$SCRATCH/pg.log" -w start >/dev/null 2>&1 && PG_PID=$(head -1 "$SCRATCH/pgdata/postmaster.pid")
    if "$PG_BIN/pg_isready" -p 55432 -q; then
      checked="$checked pg_start"
      # schema is at the expected migration head
      head=$("$PG_BIN/psql" -p 55432 -h '' -U postgres -tAc \
        "SELECT version_num FROM alembic_version" bbz 2>/dev/null || echo "?")
      [ "$head" != "?" ] && [ -n "$head" ] && checked="$checked alembic($head)" \
        || fail "alembic_version unreadable after restore"
      # every table's B-tree indexes verify (needs the amcheck extension)
      "$PG_BIN/psql" -p 55432 -h '' -U postgres -qc \
        "CREATE EXTENSION IF NOT EXISTS amcheck" bbz >/dev/null 2>&1 || true
      if "$PG_BIN/pg_amcheck" -p 55432 -h '' -U postgres --install-missing \
        --heapallindexed --parent-check -d bbz >/dev/null 2>&1; then
        checked="$checked amcheck"
      else
        fail "pg_amcheck reported corruption"
      fi
      "$PG_BIN/pg_ctl" -D "$SCRATCH/pgdata" -w stop >/dev/null 2>&1 || true
      PG_PID=""
    else
      fail "restored PostgreSQL did not start (see $SCRATCH/pg.log)"
    fi
  else
    fail "backup archive did not decrypt + extract"
  fi
fi

# --- etcd: verify the newest snapshot ---------------------------------------
newest_etcd=$(ls -1t "$BACKUP_DIR/etcd"/etcd-*.db.gpg 2>/dev/null | head -1 || true)
if [ -z "$newest_etcd" ]; then
  fail "no etcd snapshot found in $BACKUP_DIR/etcd"
else
  gpg_decrypt "$newest_etcd" > "$SCRATCH/snap.db"
  if etcdutl snapshot status "$SCRATCH/snap.db" --write-out=simple >/dev/null 2>&1 \
     || etcdctl snapshot status "$SCRATCH/snap.db" >/dev/null 2>&1; then
    checked="$checked etcd_snapshot"
  else
    fail "etcd snapshot status failed (corrupt snapshot)"
  fi
fi

rto=$(( $(date -u +%s) - started ))
log "restore test finished in ${rto}s — ok=$ok, checked:$checked"

# --- report ---------------------------------------------------------------
if [ "${DRY_RUN:-0}" = "1" ]; then
  [ "$ok" = "1" ] || exit 1
  exit 0
fi
[ -n "$API" ] && [ -n "$TOKEN" ] || die "set API and TOKEN (or DRY_RUN=1)"

body=$(printf '{"ok":%s,"checked":[%s],"detail":%s,"rto_seconds":%d}' \
  "$([ "$ok" = 1 ] && echo true || echo false)" \
  "$(echo "$checked" | tr -s ' ' '\n' | sed '/^$/d;s/.*/"&"/' | paste -sd, -)" \
  "$([ -n "$detail" ] && printf '%s' "$detail" | sed 's/"/\\"/g;s/.*/"&"/' || echo null)" \
  "$rto")
curl -fsS -X POST "$API/api/v1/system/restore-test" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "$body" >/dev/null || log "WARN: could not POST the result to $API"

[ "$ok" = "1" ] || exit 1
