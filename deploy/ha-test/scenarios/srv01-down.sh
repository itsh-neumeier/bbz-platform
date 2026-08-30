#!/usr/bin/env sh
# Scenario: BBZ-SRV01 (api1) down. The LB must keep serving from api2, writes
# must still work, and the DB must keep exactly one primary.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

before=$(event_count "$LB")
stop_svc api1

wait_for "curl -fsS -o /dev/null $LB/health/live" 30 || fail "LB unavailable after SRV01 down"
seq=$(write_event "$LB") || fail "write via LB failed with SRV01 down"
[ -n "$seq" ] || fail "no event_seq after write"
assert_single_primary

start_svc api1
wait_for "curl -fsS -o /dev/null $API1/health/ready" 90 || fail "SRV01 never became ready again"
after=$(head_seq "$API1")
[ "$after" -ge "$seq" ] || fail "SRV01 did not catch up (head $after < $seq written while down)"
[ "$(event_count "$API1")" -gt "$before" ] || fail "SRV01 missing events written while it was down"

pass "srv01-down: LB served from SRV02, writes ok, single primary, SRV01 caught up"
