import { app, BrowserWindow, shell } from 'electron';
import * as path from 'node:path';

/**
 * BBZ desktop kiosk — Electron main process (roadmap E08-01).
 *
 * ADR-0013: "the web build stays runnable in a plain browser; Electron only
 * embeds it." This process opens one hardened BrowserWindow and loads the web
 * UI from a **configurable URL** (`BBZ_WEB_URL`, default the dev server). Server
 * -load vs. a bundled `file://` is decided in E08-07; kiosk/autostart is E08-02,
 * the client/workplace id is E08-03 and agent IPC is E08-04 — none of that is
 * here yet.
 */
const WEB_URL = process.env.BBZ_WEB_URL ?? 'http://localhost:5173';

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1600,
    height: 1000,
    show: false,
    backgroundColor: '#0d1b2a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
    },
  });

  // The renderer is a web app: it must not open OS windows or navigate away
  // from the embedded origin. External links open in the user's browser.
  let appOrigin: string;
  try {
    appOrigin = new URL(WEB_URL).origin;
  } catch {
    appOrigin = '';
  }
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!appOrigin || safeOrigin(url) !== appOrigin) event.preventDefault();
  });

  win.once('ready-to-show', () => win.show());
  void win.loadURL(WEB_URL);
  return win;
}

function safeOrigin(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return '';
  }
}

// A second instance just focuses the first (full single-instance UX is E08-02).
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  void app.whenReady().then(() => {
    createWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
