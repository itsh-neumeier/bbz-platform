#!/usr/bin/env sh
# Scenario: the quorum witness (etcd3) is down. The cluster keeps quorum (2/3
# = both BBZ servers) and stays fully writable. On restart the witness rejoins.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

stop_svc etcd3

seq=$(write_event "$LB") || fail "cluster not writable with the witness down"
assert_single_primary
cluster_status "$API1" | grep -q '"quorum":true' || fail "quorum lost with only the witness down"

start_svc etcd3
wait_for "$COMPOSE exec -T etcd3 etcdctl endpoint health" 60 || fail "witness did not rejoin"
[ "$(head_seq "$LB")" -ge "$seq" ] || fail "seq regressed"

pass "witness-down: quorum held (2/3), writes ok, witness rejoined"
