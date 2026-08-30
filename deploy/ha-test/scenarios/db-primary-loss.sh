#!/usr/bin/env sh
# Scenario: the PostgreSQL primary is lost. Patroni must promote the standby;
# HAProxy re-points; writes resume within the RTO; no acknowledged event is
# lost; there is never more than one primary.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

RTO_LIMIT="${RTO_LIMIT:-60}"

old_leader=$(patroni_leader)
[ -n "$old_leader" ] || fail "could not determine the current Patroni leader"
n0=$(head_seq "$LB")
log "leader is $old_leader at head $n0"

kill_svc "$old_leader"

rto=$(rto_until_writable "$LB" 120)
log "writable again after ${rto}s"
[ "$rto" -le "$RTO_LIMIT" ] || fail "failover RTO ${rto}s > ${RTO_LIMIT}s"

assert_single_primary
new_leader=$(patroni_leader)
[ "$new_leader" != "$old_leader" ] || fail "leader did not move off $old_leader"

n1=$(head_seq "$LB")
[ "$n1" -ge "$n0" ] || fail "event_seq went backwards ($n1 < $n0) — data loss"

start_svc "$old_leader"
wait_for "[ \"\$(patroni_leader)\" = \"$new_leader\" ]" 90
assert_single_primary  # the old primary rejoined as a standby, not a second leader

pass "db-primary-loss: promoted $new_leader in ${rto}s, single primary, no seq regression"
