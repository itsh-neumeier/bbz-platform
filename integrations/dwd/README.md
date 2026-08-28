# dwd (PLACEHOLDER — no code)

DWD weather integration — the first *real* integration reference (MASTER_PROMPT
§10). **Not implemented in Phase 0** (Phase 7).

- Uses DWD's **public, documented open-data services**. The concrete endpoints
  (open-data warnings, RADOLAN radar, station observations) are selected by ADR
  at the start of Phase 7 — not guessed here.
- Target region: Mittelfranken (Nürnberg, Fürth, Erlangen, Schwabach, Ansbach,
  Neustadt a.d. Aisch).
- Capabilities: `weather.warnings`, `weather.radar`, `weather.observations`.
- Frontend consumes it for the Wetterlage page, radar timeline, operational
  assessment, and "create BBZ event from warning".
