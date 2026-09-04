import { expect, test } from '@playwright/test';

/**
 * E2E — monitor / KVM routing (roadmap E19-10 / E19-08, MASTER_PROMPT §9).
 * Backend flow: `server/tests/test_e2e_monitor_routing.py`. This is the UI half
 * (`/monitore`); wired into CI with #123.
 *
 * Skipped when no backend answers `/api/v1/meta`.
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

test('route via the select alternative, BBZ-OS locked, standard layout', async ({ page }) => {
  await page.getByRole('link', { name: 'Monitore' }).click();
  await expect(page).toHaveURL(/\/monitore$/);

  // the 3×2 grid + the large display
  await expect(page.locator('.mon__cell')).toHaveCount(7);

  // 1. change a route via the keyboard-accessible <select> (§26.14 — not drag)
  const ap3 = page.getByRole('group', { name: 'Arbeitsplatzmonitor 3' });
  await ap3.getByRole('combobox').selectOption({ label: 'Coda 1' });
  await expect(ap3.getByRole('combobox')).toHaveValue('coda1');

  // 2. the lower-left output is locked to BBZ-OS (E19-03), UI + server
  const ap4 = page.getByRole('group', { name: 'Arbeitsplatzmonitor 4' });
  await expect(ap4.getByRole('combobox')).toBeDisabled();
  await expect(ap4.locator('.mon__lock')).toBeVisible();

  // 3. save a profile, then 4. reset to the standard layout
  await page.getByLabel('Profilname').fill('Nachtdienst');
  await page.getByRole('button', { name: 'Profil speichern' }).click();

  await page.getByRole('button', { name: 'Standard-Layout' }).click();
  await expect(ap3.getByRole('combobox')).toHaveValue('bku3'); // documented default

  // 5. re-apply the saved profile
  await page.getByLabel('Profil', { exact: true }).selectOption({ label: 'Nachtdienst' });
  await page.getByRole('button', { name: 'Anwenden' }).click();
  await expect(ap3.getByRole('combobox')).toHaveValue('coda1');
});
