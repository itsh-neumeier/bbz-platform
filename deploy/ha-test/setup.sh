#!/usr/bin/env sh
# Bring the mini HA cluster up, seed the probe user, log in, write the bearer
# token to ./ .ha-token so the scenario scripts can source it.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

echo "== bringing up deploy/ha-test =="
docker compose -f compose.yml up -d --build

echo "== waiting for both API nodes to be ready =="
for base in http://localhost:8081 http://localhost:8082; do
	for _ in $(seq 1 90); do
		curl -fsS -o /dev/null "$base/health/live" && break
		sleep 2
	done
done

echo "== seeding the probe user =="
docker compose -f compose.yml exec -T api1 python /seed.py

echo "== logging in =="
TOKEN=$(curl -fsS -X POST http://localhost:8081/api/v1/auth/login \
	-H 'Content-Type: application/json' \
	-d '{"username":"ha-probe","password":"ha-probe-pw-32-bytes-minimum!!"}' \
	| grep -o '"access_token":"[^"]*"' | sed 's/.*:"//;s/"//')
[ -n "$TOKEN" ] || { echo "login failed"; exit 1; }
printf 'HA_TOKEN=%s\n' "$TOKEN" > .ha-token
echo "== ready — token in deploy/ha-test/.ha-token =="
