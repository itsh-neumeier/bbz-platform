import { expect, test } from '@playwright/test';

/**
 * E2E — archive / post-processing / reactivation reached from the Ereignis­
 * übersicht (roadmap E20-08 + E07-11/12, MASTER_PROMPT §24 steps 8–10 / §13.6).
 * Backend flow: `server/tests/test_e2e_archive_lifecycle.py`. This is the UI half
 * for the `/ereignisse` + "Nur Archiv" entry path (the Arbeitsplatz path is
 * `event-lifecycle.spec.ts`).
 *
 * Fixture: the pre-archived event from `server/scripts/seed_e2e.py`. Skipped when
 * no backend answers `/api/v1/meta`.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
});

test('archived event → full history + post-processing notes → reactivation', async ({ page }) => {
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Ereignisse' }).click();
  await expect(page).toHaveURL(/\/ereignisse$/);
  await page.getByLabel('Nur Archiv').check();

  const rows = page.locator('.events__row--archived');
  test.skip((await rows.count()) === 0, 'no archived events seeded');
  await rows.first().click();

  // the processing panel opens beside the list — same depth as an active event
  const panel = page.locator('.epp');
  await expect(panel.locator('.epp__status')).toHaveText('archiviert');
  await expect(panel.getByText('Verlauf', { exact: true })).toBeVisible();
  await expect(panel.getByText('Nachbearbeitungsnotizen')).toBeVisible();

  // reactivation needs an explicit confirm + a reason
  await panel.getByRole('button', { name: 'Reaktivieren' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Reaktivieren bestätigen' })).toBeDisabled();
  await dialog.locator('#rd-reason').fill('Rückfrage Bundespolizei');
  await dialog.getByRole('button', { name: 'Reaktivieren bestätigen' }).click();

  // back as an active event, nothing deleted
  await expect(page).toHaveURL(/\/ereignisse\/[0-9a-f-]{36}$/);
  await expect(page.locator('.epp__status')).toHaveText('in Bearbeitung');
});
