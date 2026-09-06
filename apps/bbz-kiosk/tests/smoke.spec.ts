import { test, expect, _electron as electron } from '@playwright/test';
import * as path from 'node:path';

/**
 * Smoke (E08-01 AC / Tests): the kiosk starts, loads the embedded web UI at
 * `/`, and shows the BBZ login. `BBZ_WEB_URL` points at a static build of
 * `apps/web` served for the test — no API is needed: the SPA falls back to
 * `/login` when `GET /api/v1/auth/me` fails. Also asserts the renderer has no
 * Node access and the minimal preload bridge is present.
 */
const APP_ROOT = path.join(__dirname, '..');

test('the kiosk window loads the web UI and shows the login', async () => {
  const app = await electron.launch({
    args: [APP_ROOT],
    env: {
      ...process.env,
      BBZ_WEB_URL: process.env.BBZ_WEB_URL ?? 'http://127.0.0.1:4173',
    },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState('domcontentloaded');

    // no session → the SPA redirects to /login (with a ?redirect= back to the
    // route the kiosk asked for)
    await expect(page).toHaveURL(/\/login(\?|$)/);
    await expect(page.getByLabel('Benutzername')).toBeVisible();
    await expect(page.getByLabel('Passwort')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Anmelden' })).toBeVisible();

    // the renderer is sandboxed — no Node
    const requireType = await page.evaluate(
      () => typeof (globalThis as { require?: unknown }).require,
    );
    expect(requireType).toBe('undefined');

    // the minimal preload bridge is exposed
    const isKiosk = await page.evaluate(
      () => (window as { bbzKiosk?: { isKiosk?: boolean } }).bbzKiosk?.isKiosk,
    );
    expect(isKiosk).toBe(true);
  } finally {
    await app.close();
  }
});
