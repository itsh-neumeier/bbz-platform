# bbz-kiosk (PLACEHOLDER — minimal scaffold)

Electron/Chromium kiosk client that embeds the `apps/web` build. **Not
implemented in Phase 0** (Phase 4).

Planned: autostart/kiosk mode, signed update mechanism, client/workplace id,
connection to the local `bbz-client-agent`, hardened renderer
(`contextIsolation: true`, no `nodeIntegration`, strict CSP).

The web UI is developed independently under `apps/web` and stays runnable in a
plain browser.
