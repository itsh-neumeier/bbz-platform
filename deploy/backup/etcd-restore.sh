#!/usr/bin/env sh
# Restore an encrypted etcd snapshot into a fresh data directory (E06-14).
# Rebuilds a SINGLE-member cluster from the snapshot; re-add the other members
# with `etcdctl member add` afterwards (see docs/runbooks/restore.md).
#
#   ./etcd-restore.sh /var/backups/bbz/etcd/etcd-<stamp>.db.gpg  BBZ-SRV01  https://bbz-srv01:2380  /var/lib/etcd-restore
set -eu
. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

ARCHIVE="${1:?path to an etcd-*.db.gpg}"
NAME="${2:?the member name to restore as}"
PEER_URL="${3:?this member's peer URL}"
TARGET="${4:?empty target data directory}"

[ -e "$ARCHIVE" ] || die "no such archive: $ARCHIVE"
[ -z "$(ls -A "$TARGET" 2>/dev/null || true)" ] || die "target $TARGET is not empty"

RAW=$(mktemp)
trap 'rm -f "$RAW"' EXIT
gpg_decrypt "$ARCHIVE" > "$RAW"
etcdctl snapshot status --write-out=table "$RAW" || die "not a valid etcd snapshot"

require_dir "$TARGET"
ETCDCTL_API=3 etcdctl snapshot restore "$RAW" \
	--name "$NAME" \
	--initial-cluster "$NAME=$PEER_URL" \
	--initial-advertise-peer-urls "$PEER_URL" \
	--data-dir "$TARGET/data"

log "restored to $TARGET/data as a 1-member cluster."
log "start etcd with --initial-cluster-state=existing, then 'etcdctl member add' the others."
