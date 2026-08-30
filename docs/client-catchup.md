# Client event catch-up across a node failover

MASTER_PROMPT §4: a client sends its **last known `event_seq`** on connect and
gets the missed events with no gap. This works the same whether the client
reconnects to the same node or fails over to the other one — both nodes serve
the identical, replicated `domain_events` log (ADR-0001, ADR-0011).

## `event_seq` is monotonic but **not gapless**

`domain_events.event_seq` is a PostgreSQL identity column. After a Patroni
failover the promoted node may resume numbering **past** a range of unused
values (identity allocation is cached and not replayed value-by-value). No
committed row is lost — only some numbers are skipped.

**A client must therefore track "highest `event_seq` I have seen", never "the
next number I expect".** A jump from `1042` to `1078` after a reconnect is a
failover gap, not 35 missing events.

## The handshake

1. **(re)connect** to `GET /api/v1/events/stream?after_seq=<last_seen>` (SSE)
   or `GET /ws/events?after_seq=<last_seen>` (WebSocket). Authorization
   (`events.view`) is checked **per connection** — a reconnect re-authorises.
2. The server replays every row with `event_seq > after_seq`, in order.
3. When the backlog is drained the server sends one control frame:
   * SSE: `event: caught_up` / `data: {"head": <seq>}`
   * WS: `{"type": "caught_up", "head": <seq>}`

   The client now holds everything through `head` and switches to live mode.
4. Live events follow as `event:` / `{"type":"event"}` frames; `: heartbeat` /
   `{"type":"heartbeat"}` keep the connection warm.

On any disconnect the client repeats from step 1 with the highest `event_seq`
it has processed.

## Cheap "am I behind?" check

`GET /api/v1/events/stream/head` → `{"event_seq": <seq>}` — the current head on
that node. A client (or the agent's server-selection logic) can poll this and
compare to its last-seen seq without opening a stream. The value is identical
on every node once replicated.

## What the server guarantees

* Every committed event with `event_seq > after_seq` is delivered exactly once,
  in `event_seq` order, before `caught_up`.
* `caught_up.head` is a lower bound on "you are current" — never claims more
  than was actually sent.
* The in-process broker only *shortens* the poll wait; a lost wake-up is caught
  by the 15 s poll, so a node restart mid-stream cannot drop an event.
