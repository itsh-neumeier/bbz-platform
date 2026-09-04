import { expect, test } from '@playwright/test';

/**
 * E2E — login / session / logout (roadmap E07-02, MASTER_PROMPT §11).
 *
 * Requires a running backend with a local account. Against the dev compose
 * stack that is `admin` / `Wolke7-Bahnhof!x`; override with `E2E_USER` /
 * `E2E_PASS`. Skipped automatically when no backend answers `/api/v1/meta`
 * (e.g. a bare `npm run e2e`). Wired into CI with the mandatory event-lifecycle
 * suite, #123.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

test('unauthenticated navigation redirects to /login and back after login', async ({ page }) => {
  await page.goto('/arbeitsplatz');
  await expect(page).toHaveURL(/\/login\?redirect=(%2F|\/)arbeitsplatz/);

  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();

  await expect(page).toHaveURL(/\/arbeitsplatz$/);
  await expect(page.locator('.topbar__crumb')).toContainText('Arbeitsplatz');
  await expect(page.locator('.wp__store')).toBeVisible(); // the Ereignisspeicher
});

test('wrong credentials show a German error and stay on /login', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill('definitely-wrong');
  await page.getByRole('button', { name: 'Anmelden' }).click();

  await expect(page.getByRole('alert')).toContainText(/Benutzername oder Passwort/);
  await expect(page).toHaveURL(/\/login/);
});

test('logout returns to /login and the session no longer restores', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);

  await page.getByRole('button', { name: 'Abmelden' }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto('/arbeitsplatz');
  await expect(page).toHaveURL(/\/login/);
});

test('after login the Ereignisübersicht lists events and opens one', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);

  await page.locator('.sidebar__nav').getByRole('link', { name: 'Ereignisse' }).click();
  await expect(page).toHaveURL(/\/ereignisse$/);

  const rows = page.locator('.events__row');
  await expect(rows.first()).toBeVisible();

  // selecting a row opens the shared processing panel beside the list
  await rows.first().click();
  await expect(page.locator('.epp')).toBeVisible();
  await expect(page.locator('.epp').getByText('Verlauf', { exact: true })).toBeVisible();
});
