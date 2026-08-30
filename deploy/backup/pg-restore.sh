#!/usr/bin/env sh
# Restore an encrypted PostgreSQL base backup into a fresh data directory
# (roadmap E06-14). PITR (replay WAL to a target time) is a pgBackRest job in
# production; here we restore the base and let Patroni/archive recovery continue.
#
#   GPG_RECIPIENT=<key>  ./pg-restore.sh /var/backups/bbz/postgres/base-<stamp>.tar.gz.gpg  /var/lib/postgresql/restore
set -eu
. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

ARCHIVE="${1:?path to a base-*.tar.gz.gpg}"
TARGET="${2:?empty target data directory}"

[ -e "$ARCHIVE" ] || die "no such archive: $ARCHIVE"
[ -z "$(ls -A "$TARGET" 2>/dev/null || true)" ] || die "target $TARGET is not empty"

require_dir "$TARGET"
log "restoring $ARCHIVE -> $TARGET"
gpg_decrypt "$ARCHIVE" | tar -xz -C "$TARGET"

# pg_basebackup --format=tar puts base.tar.gz + pg_wal.tar.gz when streamed;
# with --pgdata=- the single tar already contains PGDATA + streamed WAL.
[ -f "$TARGET/PG_VERSION" ] || die "restore did not produce a valid PGDATA (no PG_VERSION)"
chmod 700 "$TARGET"

cat > "$TARGET/postgresql.auto.conf.restore" <<'EOF'
# review before starting: point restore_command at your WAL archive for PITR,
# or leave it to Patroni to rejoin the cluster and stream from the primary.
# restore_command = 'gpg --decrypt /var/backups/bbz/postgres/wal/%f.gpg > %p'
EOF

log "restored. verify: start PG read-only, run SELECT count(*) FROM audit_events;"
