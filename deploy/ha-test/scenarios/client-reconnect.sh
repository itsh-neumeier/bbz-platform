#!/usr/bin/env sh
# Scenario: a streaming client is served by one node; that node dies; the
# client reconnects to the other node with its last event_seq and gets a
# gap-free continuation (the E06-07 catch-up protocol) — no lost, no dup.
. "$(dirname -- "$0")/../lib.sh"
. "$(dirname -- "$0")/../.ha-token"

# consume the stream from api1 until the caught_up marker, record the head
before=$(
	_auth -N "$API1/api/v1/events/stream?after_seq=0" \
		| sed -n '/event: caught_up/{n;p;q}' | grep -o '[0-9]\{1,\}'
)
[ -n "$before" ] || fail "no caught_up marker from api1"
log "client caught up at seq $before on SRV01"

stop_svc api1
# events happen while the client is disconnected
w1=$(write_event "$API2"); w2=$(write_event "$API2")

# reconnect to api2 from the last seen seq
missed=$(
	_auth -N "$API2/api/v1/events/stream?after_seq=$before" \
		| grep -c '^id: ' || true
)
[ "$missed" -ge 2 ] || fail "reconnect replayed $missed events, expected the 2 missed"
last=$(head_seq "$API2")
[ "$last" -ge "$w2" ] && [ "$w2" -ge "$w1" ] || fail "seq ordering broken across the failover"

start_svc api1
pass "client-reconnect: SRV02 replayed the $missed missed events from seq $before, gap-free"
