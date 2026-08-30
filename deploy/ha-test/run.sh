#!/usr/bin/env sh
# Run every HA failure scenario against the mini cluster (roadmap E06-11).
#
#   ./run.sh                 # setup + all scenarios + teardown
#   ./run.sh srv01-down      # one scenario (cluster must already be up)
#   KEEP=1 ./run.sh          # leave the cluster running afterwards
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

SCENARIOS="srv01-down srv02-down db-primary-loss net-isolation witness-down client-reconnect recovery"

if [ $# -gt 0 ]; then
	sh "scenarios/$1.sh"
	exit $?
fi

./setup.sh
trap '[ "${KEEP:-0}" = 1 ] || docker compose -f compose.yml down -v' EXIT

rc=0
for name in $SCENARIOS; do
	printf '\n=== %s ===\n' "$name"
	if sh "scenarios/$name.sh"; then :; else rc=1; printf 'SCENARIO FAILED: %s\n' "$name"; fi
	# let the cluster settle between scenarios
	sh -c '. ./lib.sh; . ./.ha-token; wait_for "curl -fsS -o /dev/null $LB/health/ready" 120' || true
done

printf '\n=== %s ===\n' "$([ "$rc" = 0 ] && echo 'ALL SCENARIOS PASSED' || echo 'SOME SCENARIOS FAILED')"
exit "$rc"
