#!/usr/bin/env sh
# Take a consistent etcd snapshot. A cron/systemd-timer hook calls this; the
# retention + off-host copy + restore drill are E06-15 (#95).
#
#   OUT=/var/backups/etcd ./snapshot.sh
set -eu

CERTS="${CERTS:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/certs}"
ENDPOINT="${ENDPOINT:-https://127.0.0.1:2379}"
OUT="${OUT:-./etcd-backups}"
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$OUT/etcd-$STAMP.db"

ETCDCTL_API=3 etcdctl --endpoints="$ENDPOINT" \
  --cacert="$CERTS/ca.crt" \
  --cert="$CERTS/client-admin.crt" \
  --key="$CERTS/client-admin.key" \
  snapshot save "$FILE"

etcdctl snapshot status --write-out=table "$FILE"
echo "snapshot -> $FILE"
