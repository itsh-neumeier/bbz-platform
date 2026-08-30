#!/usr/bin/env sh
# Encrypted etcd snapshot (roadmap E06-14). Wraps deploy/etcd/snapshot.sh, then
# encrypts and prunes. etcd holds cluster metadata (Patroni state, app leader
# leases) — small, but losing it means a manual cluster rebuild.
#
#   GPG_RECIPIENT=<key>  ETCD_ENDPOINT=https://bbz-srv01:2379  CERTS=/opt/bbz/deploy/etcd/certs  ./etcd-backup.sh
set -eu
. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

ETCD_ENDPOINT="${ETCD_ENDPOINT:-https://127.0.0.1:2379}"
CERTS="${CERTS:-/opt/bbz/deploy/etcd/certs}"
OUT="$BACKUP_DIR/etcd"
require_dir "$OUT"

STAMP=$(ts)
RAW=$(mktemp)
trap 'rm -f "$RAW"' EXIT
FILE="$OUT/etcd-$STAMP.db.gpg"

log "snapshot $ETCD_ENDPOINT -> $FILE"
ETCDCTL_API=3 etcdctl --endpoints="$ETCD_ENDPOINT" \
	--cacert="$CERTS/ca.crt" --cert="$CERTS/client-admin.crt" --key="$CERTS/client-admin.key" \
	snapshot save "$RAW"
etcdctl snapshot status --write-out=table "$RAW"

gpg_encrypt "$FILE" < "$RAW"
gpg_decrypt "$FILE" > "$RAW.check" && etcdctl snapshot status "$RAW.check" >/dev/null \
	|| die "snapshot $FILE failed its integrity check"
rm -f "$RAW.check"
log "integrity ok"

prune "$OUT" "etcd-*.db.gpg"
log "done."
