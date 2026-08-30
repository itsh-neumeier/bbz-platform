# shellcheck shell=sh
# Shared helpers for the HA failure-scenario harness (E06-11).
# Sourced by every scenarios/*.sh. Assumes `docker compose` in this directory.
set -eu

COMPOSE="docker compose -f $(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/compose.yml"
API1="http://localhost:8081"   # published per-node ports (see compose override below)
API2="http://localhost:8082"
LB="http://localhost:8080"
TOKEN="${HA_TOKEN:-}"          # bearer with events.create + system.cluster.view

log()  { printf '  %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$1"; }

# wait until `cmd` succeeds, up to $2 seconds (default 60)
wait_for() {
	deadline=$(( $(date +%s) + ${2:-60} ))
	while [ "$(date +%s)" -lt "$deadline" ]; do
		if eval "$1" >/dev/null 2>&1; then return 0; fi
		sleep 2
	done
	return 1
}

_auth() { curl -fsS -H "Authorization: Bearer $TOKEN" "$@"; }

# write one event via $1 (API base); echo the resulting event_seq
write_event() {
	_auth -X POST "$1/api/v1/events" -H 'Content-Type: application/json' \
		-H "X-Command-Id: $(cat /proc/sys/kernel/random/uuid)" \
		-d '{"title":"ha probe","priority":"low"}' >/dev/null
	_auth "$1/api/v1/events/stream/head" | grep -o '"event_seq":[0-9]*' | grep -o '[0-9]*'
}

head_seq() { _auth "$1/api/v1/events/stream/head" | grep -o '"event_seq":[0-9]*' | grep -o '[0-9]*'; }

# number of events visible via $1 (first page is enough for the harness)
event_count() { _auth "$1/api/v1/events?limit=200" | grep -o '"id"' | wc -l | tr -d ' '; }

# stop / start / isolate a compose service by name
stop_svc()      { log "stop $1";      $COMPOSE stop "$1" >/dev/null; }
start_svc()     { log "start $1";     $COMPOSE start "$1" >/dev/null; }
kill_svc()      { log "kill $1";      $COMPOSE kill "$1" >/dev/null; }
isolate_svc()   { log "isolate $1";   docker network disconnect "${COMPOSE_PROJECT:-bbz-ha-test}_default" "$1" 2>/dev/null || true; }
rejoin_svc()    { log "rejoin $1";    docker network connect    "${COMPOSE_PROJECT:-bbz-ha-test}_default" "$1" 2>/dev/null || true; }

# which pg node is the Patroni leader right now
patroni_leader() {
	$COMPOSE exec -T pg1 patronictl list -f json 2>/dev/null \
		| tr ',' '\n' | grep -B2 '"Role": *"Leader"' | grep '"Member"' \
		| head -n1 | sed 's/.*: *"//;s/".*//'
}

# the Patroni cluster must have exactly ONE leader (no split brain)
assert_single_primary() {
	leaders=$($COMPOSE exec -T pg1 patronictl list -f json 2>/dev/null \
		| grep -o '"Role": *"[^"]*"' | grep -c 'Leader' || true)
	[ "$leaders" = "1" ] || fail "expected exactly 1 Patroni leader, found $leaders (split brain?)"
}

# measured failover RTO: seconds until a write succeeds again
rto_until_writable() {
	start=$(date +%s)
	wait_for "write_event $1" "${2:-90}" || fail "cluster never became writable again"
	echo $(( $(date +%s) - start ))
}

cluster_status() { _auth "$1/cluster/status"; }
