#!/usr/bin/env sh
# Scenario: one BBZ server is network-isolated (its api + pg lose the shared
# network). The other server + the witness keep quorum and keep serving; the
# isolated pg must NOT promote itself (no split brain). On reconnect it rejoins
# as a standby.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

leader=$(patroni_leader)
# isolate the node that does NOT hold the leader, so the leader side keeps quorum
victim_pg=$( [ "$leader" = "pg1" ] && echo pg2 || echo pg1 )
victim_api=$( [ "$victim_pg" = "pg1" ] && echo api1 || echo api2 )
survivor_api=$( [ "$victim_api" = "api1" ] && echo "$API2" || echo "$API1" )

isolate_svc "$victim_pg"
isolate_svc "$victim_api"

wait_for "curl -fsS -o /dev/null $survivor_api/health/ready" 30 || fail "survivor not ready during isolation"
seq=$(write_event "$survivor_api") || fail "survivor could not write during isolation"
assert_single_primary  # the isolated node must not have become a second leader

rejoin_svc "$victim_pg"
rejoin_svc "$victim_api"
wait_for "curl -fsS -o /dev/null http://localhost:8081/health/live && curl -fsS -o /dev/null http://localhost:8082/health/live" 90
assert_single_primary
[ "$(head_seq "$survivor_api")" -ge "$seq" ] || fail "seq regressed after rejoin"

pass "net-isolation: survivor kept serving, no split brain, isolated node rejoined as standby"
