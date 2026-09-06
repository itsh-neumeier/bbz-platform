# bbz-kiosk — BBZ desktop client (Electron)

Electron shell that **embeds** the `apps/web` build in one hardened
BrowserWindow (ADR-0013: "the web build stays runnable in a plain browser;
Electron only embeds it"). The web UI is developed independently under
`apps/web`.

## Status (E08-01 — scaffold)

Done: the Electron base project — `contextIsolation: true`, `sandbox: true`, no
`nodeIntegration`, a minimal read-only preload bridge (`window.bbzKiosk`),
external links open in the OS browser, cross-origin navigation is blocked, a
single-instance lock focuses the running window.

**Not yet:** kiosk / autostart mode (E08-02), client / workplace-id
provisioning (E08-03), local `bbz-client-agent` IPC (E08-04), signed update
mechanism (E08-05), crash/relaunch watchdog (E08-06), the server-load-vs-bundle
decision + signed CI build (E08-07 / ADR-0022).

## Run

```sh
npm ci
npm run build          # tsc → dist/
BBZ_WEB_URL=http://localhost:5173 npm start
```

`BBZ_WEB_URL` is the web UI to load (default `http://localhost:5173`, the Vite
dev server). Point it at the Caddy edge for a full local stack.

## Checks

```sh
npm run lint
npm run typecheck
npm test               # Playwright _electron smoke — needs a served apps/web build
```

The smoke test expects a static `apps/web` build served on `BBZ_WEB_URL`
(default `http://127.0.0.1:4173`); on Linux it runs under `xvfb`.
