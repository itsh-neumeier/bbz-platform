import { expect, test } from '@playwright/test';

/**
 * E2E — the operator shell's live surfaces:
 *  - #101 (E07-05) the SSE sync indicator
 *  - #117 (E07-13) the topbar priority banner for unaccepted critical events
 *  - #105 (E07-07) the critical-row pulse + `prefers-reduced-motion`
 *  - #125 (E07-17) the theme toggle
 *
 * Fixtures: `server/scripts/seed_e2e.py`. Skipped when no backend answers
 * `/api/v1/meta`.
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

test('the SSE sync indicator reaches "verbunden" (#101)', async ({ page }) => {
  const sync = page.locator('.sync');
  await expect(sync).toHaveClass(/sync--connected/, { timeout: 15_000 });
  await expect(sync).toContainText('verbunden');
});

test('the topbar priority banner lists unaccepted critical events and jumps to one (#117)', async ({
  page,
}) => {
  // the banner is deliberately hidden on the Arbeitsplatz / Ereignisse (the
  // Ereignisspeicher is already the whole view) — check it on another page
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Telefonbuch' }).click();
  await expect(page).toHaveURL(/\/telefonbuch$/);

  const banner = page.locator('.palert');
  await expect(banner).toBeVisible();
  await banner.click();
  await expect(page).toHaveURL(/\/ereignisse\/[0-9a-f-]{36}$/);
  await expect(page.locator('.epp')).toBeVisible();
});

test('critical rows pulse, and prefers-reduced-motion shortens the animation to nothing (#105)', async ({
  page,
}) => {
  const row = page.locator('.wp__row--critical').first();
  await expect(row).toBeVisible();

  const dur = await row.evaluate((el) => getComputedStyle(el).animationDuration);
  expect(dur).not.toBe('0s');
  const name = await row.evaluate((el) => getComputedStyle(el).animationName);
  expect(name).not.toBe('none');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  const reduced = await row.evaluate((el) => getComputedStyle(el).animationDuration);
  expect(parseFloat(reduced)).toBeLessThan(0.01); // 0.001ms — the global rule
});

test('the theme toggle cycles data-mode on <html> (#125)', async ({ page }) => {
  const html = page.locator('html');
  const toggle = page.getByRole('button', { name: /Darstellung:/ });

  await expect(html).not.toHaveAttribute('data-mode', /.+/); // system = no attribute
  await toggle.click();
  await expect(html).toHaveAttribute('data-mode', 'light');
  await toggle.click();
  await expect(html).toHaveAttribute('data-mode', 'dark');
  await toggle.click();
  await expect(html).not.toHaveAttribute('data-mode', /.+/);
});
