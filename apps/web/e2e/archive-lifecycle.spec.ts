import { expect, test } from '@playwright/test';

/**
 * E2E — archive / post-processing / reactivation (roadmap E20-08 + E07-11/12,
 * MASTER_PROMPT §24 steps 8–10 / §13.6). Backend flow: covered by
 * `server/tests/test_e2e_archive_lifecycle.py`. This is the UI half; wired into
 * CI with #123.
 *
 * Requires the dev stack with a `local` account and at least one archived
 * event. Skipped when no backend answers `/api/v1/meta`.
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
  await page.getByRole('link', { name: 'Archiv' }).click();
  await expect(page).toHaveURL(/\/archiv$/);

  const rows = page.locator('.arch__row');
  test.skip((await rows.count()) === 0, 'no archived events seeded');

  await rows.first().click();
  await expect(page).toHaveURL(/\/archiv\/[0-9a-f-]{36}$/);

  // the same depth of history as an active event, plus the workflow panel
  await expect(page.getByText('archiviert')).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Verlauf' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Maßnahmen' })).toBeVisible();
  await expect(
    page.getByRole('heading', { level: 2, name: 'Nachbearbeitungsnotizen' }),
  ).toBeVisible();

  // reactivation needs an explicit confirm + a reason
  await page.getByRole('button', { name: 'Reaktivieren' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // the confirm button is disabled until a reason is entered
  await expect(dialog.getByRole('button', { name: 'Reaktivieren bestätigen' })).toBeDisabled();
  await dialog.locator('#rd-reason').fill('Rückfrage Bundespolizei');
  await dialog.getByRole('button', { name: 'Reaktivieren bestätigen' }).click();

  // back as an active event, nothing deleted
  await expect(page).toHaveURL(/\/ereignisse\/[0-9a-f-]{36}$/);
  await expect(page.locator('.detail__status')).toContainText('Bearbeitung');
});
