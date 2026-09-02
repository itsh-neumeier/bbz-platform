#!/usr/bin/env sh
# Rolling update of the two BBZ application nodes with health gates
# (MASTER_PROMPT §21, docs/runbooks/rolling-update.md). Run from a control host
# that can reach the API and SSH the nodes.
#
#   NODES="bbz-srv02 bbz-srv01"                # passive/standby node FIRST
#   IMAGE="ghcr.io/itsh-neumeier/bbz-api@sha256:<digest>"   # signed digest only
#   API="https://bbz.example.internal"
#   TOKEN="<bearer token with system.cluster.manage>"
#   MIGRATION_CHECKED=1                        # CI's migration-compat job is green
#     ./rolling-update.sh
#
# Aborts non-zero on any failed pre-flight or health gate; nodes not yet
# updated are left untouched (see rollback.md).
set -eu

: "${NODES:?space-separated node hosts, passive node first}"
: "${IMAGE:?new image digest (ghcr...@sha256:...)}"
: "${API:?base URL, e.g. https://bbz.example.internal}"
: "${TOKEN:?bearer token with system.cluster.manage}"

HEALTH_TMPL="${HEALTH_TMPL:-https://%s/health/ready}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/bbz/deploy/node}"
LAG_LIMIT="${LAG_LIMIT:-1048576}"        # 1 MiB — matches maximum_lag_on_failover
GATE_RETRIES="${GATE_RETRIES:-30}"
GATE_SLEEP="${GATE_SLEEP:-4}"

_api() { curl -fsS -H "Authorization: Bearer $TOKEN" "$@"; }

case "$IMAGE" in
  *@sha256:*) : ;;
  *) echo "refusing: IMAGE must be pinned by digest (@sha256:...), got '$IMAGE'"; exit 2 ;;
esac

preflight() {
  s=$(_api "$API/cluster/status") || { echo "  cluster/status unreachable"; return 1; }
  echo "$s" | grep -q '"stub":false'       || { echo "  cluster/status is a stub"; return 1; }
  echo "$s" | grep -q '"dcs_healthy":true' || { echo "  DCS not healthy"; return 1; }
  echo "$s" | grep -q '"quorum":true'      || { echo "  no etcd quorum"; return 1; }
  for lag in $(echo "$s" | grep -o '"replication_lag_bytes":[0-9]\{1,\}' | grep -o '[0-9]\{1,\}'); do
    [ "$lag" -le "$LAG_LIMIT" ] || { echo "  replication lag ${lag}B > ${LAG_LIMIT}B"; return 1; }
  done
  [ "${MIGRATION_CHECKED:-0}" = "1" ] || {
    echo "  set MIGRATION_CHECKED=1 once CI's migration-compat job is green for this digest"
    return 1
  }
}

health_gate() {
  url=$(printf "$HEALTH_TMPL" "$1")
  i=0
  while [ "$i" -lt "$GATE_RETRIES" ]; do
    if curl -fsS -o /dev/null "$url"; then echo "  $1 /health/ready green"; return 0; fi
    i=$((i + 1)); sleep "$GATE_SLEEP"
  done
  echo "  $1 did not become ready within $((GATE_RETRIES * GATE_SLEEP))s"
  return 1
}

deploy_node() {
  echo "  pulling + starting $IMAGE on $1"
  ssh "$1" "set -e; cd '$DEPLOY_DIR'; \
    sed -i.bak 's|^BBZ_API_IMAGE=.*|BBZ_API_IMAGE=$IMAGE|' .env; \
    sh preflight.sh; \
    docker compose pull api; \
    docker compose up -d --no-deps api"
}

marker() {
  _api -X POST "$API/api/v1/system/rolling-update" -H 'Content-Type: application/json' \
    -d "{\"phase\":\"$1\",\"image\":\"$IMAGE\"}" >/dev/null
}

echo "== pre-flight =="
preflight || { echo "ABORT: pre-flight failed, nothing changed"; exit 1; }
marker started
trap 'echo "== INTERRUPTED — check node state, see rollback.md =="' INT TERM

for node in $NODES; do
  echo "== $node =="
  deploy_node "$node"
  health_gate "$node" || { echo "ABORT: $node unhealthy; later nodes untouched (rollback.md)"; exit 1; }
  echo "  re-checking cluster"
  preflight || { echo "ABORT: cluster unhealthy after $node; later nodes untouched"; exit 1; }
done

marker completed
echo "== done: all nodes on $IMAGE, cluster healthy =="
