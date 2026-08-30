#!/usr/bin/env sh
# Encrypted PostgreSQL base backup + WAL (roadmap E06-14).
#
# The *intended* production tool is pgBackRest (incremental, parallel, built-in
# retention and PITR). This script is the dependency-light stand-in and the
# reference for what a backup must produce:
#   - a consistent base backup, gpg-encrypted, 0600
#   - the archived WAL segments since the last base backup
#   - RPO = the WAL archive interval (archive_timeout, default 60s) — a Leitstelle
#     loses at most that much on a total primary loss with an intact archive.
#
#   GPG_RECIPIENT=<key>  PGHOST=pg-primary  ./pg-backup.sh
set -eu
. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
OUT="$BACKUP_DIR/postgres"
require_dir "$OUT"

STAMP=$(ts)
FILE="$OUT/base-$STAMP.tar.gz.gpg"

log "base backup of $PGHOST:$PGPORT -> $FILE"
pg_basebackup \
	--host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
	--wal-method=stream --checkpoint=fast --format=tar --gzip --pgdata=- \
	| gpg_encrypt "$FILE"

# integrity: the encrypted archive must decrypt and be a valid gzip stream
gpg_decrypt "$FILE" | gzip -t || die "backup $FILE failed its integrity check"
log "integrity ok"

prune "$OUT" "base-*.tar.gz.gpg"
log "done. RPO = archive_timeout (WAL archive interval)."
