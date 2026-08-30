#!/usr/bin/env sh
# Scenario: full cluster restart. After everything comes back the cluster
# converges to one primary and no acknowledged event is lost.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

# write a marker batch, remember the head
i=0
while [ "$i" -lt 5 ]; do write_event "$LB" >/dev/null; i=$((i + 1)); done
n0=$(head_seq "$LB")
c0=$(event_count "$LB")

log "stopping the whole cluster"
$COMPOSE stop >/dev/null
log "starting it again"
$COMPOSE start >/dev/null

wait_for "curl -fsS -o /dev/null $LB/health/ready" 180 || fail "cluster did not become ready after restart"
wait_for "[ -n \"\$(patroni_leader)\" ]" 120 || fail "no Patroni leader after restart"
assert_single_primary

n1=$(head_seq "$LB")
[ "$n1" -ge "$n0" ] || fail "head_seq regressed after restart ($n1 < $n0)"
[ "$(event_count "$LB")" -ge "$c0" ] || fail "events lost across the restart"

pass "recovery: cluster converged to one primary, all $c0 events survived the restart"
