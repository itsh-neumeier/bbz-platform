# Functional mockup

`bbz-3sz-v10.html` is the client-supplied functional HTML mockup (version V10).

Per `MASTER_PROMPT_CLAUDE_CODE.md` §13 and `.ai/FEATURES.md` it is the
**binding UX reference** for the operator web UI (Epic 07): layout, content,
interaction, and the priority animations. ADR-0013 requires mockup parity to be
tracked explicitly — see `docs/mockup-parity-checklist.md`.

This closes the long-open **E01-02** ("client must supply the functional HTML
mockup files").

## Reading it

Open the file in a browser. It is a single self-contained page with mock data
and works offline. The one external reference — the DB logo — has been changed
from a `static-bahn.de` hotlink to `/brand/db-logo.svg` (the licensed asset is
not redistributed; the `#dbFallback` "DB" wordmark shows when it is absent).

## Relationship to the real app

The real frontend (`apps/web/`) is **not** a 1:1 port. It keeps the mockup's
**layout and content** but renders it with the DB UX Design System v3 tokens
(ADR-0029) instead of the mockup's ad-hoc dark palette, and it is wired to the
real backend. Two deliberate deviations:

- **No "+ Ereignis anlegen" button** — events are created only by documented
  triggers (BMA / call / Coda / weather). See ADR-0030.
- Mockup-only views without a backend (Anrufe page, Schichtbuch, Auswertung)
  are not built yet.

The migration is phased; `docs/mockup-parity-checklist.md` tracks each row.
