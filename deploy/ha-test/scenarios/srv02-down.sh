#!/usr/bin/env sh
# Scenario: BBZ-SRV02 (api2) down. Symmetric to srv01-down.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

stop_svc api2

wait_for "curl -fsS -o /dev/null $LB/health/live" 30 || fail "LB unavailable after SRV02 down"
seq=$(write_event "$LB") || fail "write via LB failed with SRV02 down"
assert_single_primary

start_svc api2
wait_for "curl -fsS -o /dev/null $API2/health/ready" 90 || fail "SRV02 never became ready again"
[ "$(head_seq "$API2")" -ge "$seq" ] || fail "SRV02 did not catch up"

pass "srv02-down: LB served from SRV01, writes ok, single primary, SRV02 caught up"
