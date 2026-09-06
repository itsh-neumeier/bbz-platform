import { contextBridge } from 'electron';

/**
 * Minimal preload bridge (E08-01). `contextIsolation` is on and the renderer
 * has no Node access; this exposes a tiny, read-only marker so the web UI can
 * tell it is running inside the kiosk (it treats `window.bbzKiosk` as optional,
 * ADR-0013). The real surface — agent IPC (E08-04), client/workplace id
 * (E08-03) — is deliberately not here yet.
 */
export interface BbzKioskBridge {
  readonly isKiosk: true;
  readonly platform: NodeJS.Platform;
}

const bridge: BbzKioskBridge = {
  isKiosk: true,
  platform: process.platform,
};

contextBridge.exposeInMainWorld('bbzKiosk', bridge);
