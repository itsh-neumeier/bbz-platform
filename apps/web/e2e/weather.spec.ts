import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — Wetterlage page (E18-09 / #391). The backend (E18-05..08) is complete;
 * `WeatherPage.vue` was only ever a stub. The issue's Tests field asks for
 * exactly this: "Radar scrubben (Tastatur), Warnung → Ereignis erzeugen."
 *
 * `seed_e2e.py` seeds one active DWD warning (STURMBÖEN / Nürnberg) + a few
 * observations. Radar frames are a per-node in-memory cache (E18-03) with no
 * live DWD in CI, so the radar-scrub test stubs `GET /weather/radar`.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await login(page);
});

test('turns a DWD warning into a BBZ event through the confirmation dialog (#391)', async ({
  page,
}) => {
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Wetterlage' }).click();
  await expect(page).toHaveURL(/\/wetterlage$/);

  const alert = page.locator('.wx__alert').filter({ hasText: 'STURMBÖEN' }).first();
  await expect(alert).toBeVisible();

  await alert.getByRole('button', { name: 'Ereignis erzeugen' }).click();

  const dialog = page.locator('.wxd__form');
  await expect(dialog).toBeVisible();
  // priority pre-filled from DWD warn level 3 → "hoch"
  await expect(dialog.locator('#wxd-prio')).toHaveValue('high');
  await dialog.locator('#wxd-assessment').fill('E2E: Lage am Hauptbahnhof beobachten.');

  await Promise.all([
    page.waitForURL(/\/ereignisse\/[0-9a-f-]{36}$/),
    dialog.getByRole('button', { name: 'Ereignis erzeugen' }).click(),
  ]);

  // the new event carries the warning headline as its title
  await expect(page.locator('body')).toContainText('STURMBÖEN');
});

test('radar timeline scrubs and plays without a mouse (#391)', async ({ page }) => {
  const frames = Array.from({ length: 6 }, (_, i) => ({
    frame_time: `2026-09-05T1${i}:00:00Z`,
    image_ref: `https://maps.dwd.de/geoserver/wms?frame=${i}`,
  }));
  await page.route('**/api/v1/weather/radar*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        attribution: 'Deutscher Wetterdienst',
        health: { overall: 'ok', checked_at: '2026-09-05T12:00:00Z', kinds: [] },
        area: 'mittelfranken',
        frames,
      }),
    }),
  );

  await page.locator('.sidebar__nav').getByRole('link', { name: 'Wetterlage' }).click();
  await expect(page).toHaveURL(/\/wetterlage$/);

  const scrub = page.locator('#wx-radar-scrub');
  await expect(scrub).toBeVisible();
  await expect(page.locator('.rt__pos')).toHaveText('Bild 6 von 6');

  // keyboard-only: focus the slider, step back a frame, jump to the start
  await scrub.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.locator('.rt__pos')).toHaveText('Bild 5 von 6');
  await page.keyboard.press('Home');
  await expect(page.locator('.rt__pos')).toHaveText('Bild 1 von 6');

  // play / pause is a native button
  await page.getByRole('button', { name: 'Abspielen' }).click();
  await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible();
  await page.getByRole('button', { name: 'Pause' }).click();
  await expect(page.getByRole('button', { name: 'Abspielen' })).toBeVisible();
});
