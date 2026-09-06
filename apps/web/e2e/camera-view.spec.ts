import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — camera panel in the event detail (E16-12 / #357, MASTER_PROMPT §31/§36).
 *
 * The panel lists the cameras the trigger engine associated with the event
 * (CAMERA_OPENED / CAMERA_ACTION_FAILED trail, ADR-0032) with their live status,
 * and must never block working the event. `seed_e2e.py` seeds one event with a
 * camera trail; the online/offline states are covered by stubbing the endpoint
 * (the CI mock video provider has no simulated cameras, so every ref resolves as
 * "Status unbekannt").
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const CAMERA_EVENT = 'Überfall SP Nürnberg — E2E-Kamera';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

async function openCameraEvent(page: Page) {
  const row = page.locator('.wp__row').filter({ hasText: CAMERA_EVENT });
  await expect(row).toBeVisible();
  await row.click();
  const panel = page.locator('.epp');
  await expect(panel.getByRole('heading', { name: CAMERA_EVENT })).toBeVisible();
  return panel;
}

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await login(page);
});

test('lists the associated cameras and never blocks working the event (#357)', async ({ page }) => {
  const panel = await openCameraEvent(page);

  const cams = panel.locator('.campanel');
  await expect(cams.locator('.card-title')).toHaveText('Kameras');
  await expect(cams.locator('.campanel__item')).toHaveCount(2);
  // CAM-SP-NBG-02 failed to open — called out as text, not just colour
  await expect(
    cams.locator('.campanel__item').filter({ hasText: 'CAM-SP-NBG-02' }),
  ).toContainText('Öffnen fehlgeschlagen');

  // the camera panel does not stop the operator accepting the event
  await panel.locator('.epp__actions').getByRole('button', { name: 'Annehmen' }).click();
  await expect(panel.locator('.epp__status')).toHaveText('angenommen');
  await expect(cams).toBeVisible();
});

test('shows online / offline status and the degraded state (#357)', async ({ page }) => {
  await page.route('**/api/v1/events/*/cameras', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider_available: false,
        cameras: [
          {
            ref: 'CAM-A',
            name: 'Bahnsteig Nord',
            site: 'SP Nürnberg',
            online: true,
            group_ids: [],
            last_action_state: 'opened',
          },
          {
            ref: 'CAM-B',
            name: 'Halle 7',
            site: null,
            online: false,
            group_ids: [],
            last_action_state: 'opened',
          },
        ],
      }),
    }),
  );

  const panel = await openCameraEvent(page);
  const cams = panel.locator('.campanel');

  await expect(cams.locator('.campanel__down')).toHaveText('Video derzeit nicht verfügbar.');
  await expect(cams.locator('.campanel__item').filter({ hasText: 'Bahnsteig Nord' })).toContainText(
    'verfügbar',
  );
  await expect(cams.locator('.campanel__item').filter({ hasText: 'Halle 7' })).toContainText(
    'offline',
  );
});
