import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — monitor / KVM routing dialog (E19-08 / #408, MASTER_PROMPT §9/§26.14).
 * Backend flow: `server/tests/test_e2e_monitor_routing.py`.
 *
 * The dialog is reached at `/monitore` (sidebar + topbar both push there). The
 * `monitor_*` schema + standard layout come from migration 0042; `monitor_mock`
 * is the active provider in CI. AC: full operation without a mouse; the
 * lower-left output not changeable; a11y green.
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

async function routeVia(page: Page, group: ReturnType<Page['getByRole']>, label: string) {
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/v1/monitor/routes') && r.request().method() === 'PUT',
    ),
    group.getByRole('combobox').selectOption({ label }),
  ]);
}

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await login(page);
  // known baseline — a prior spec in the workers:1 run may have moved routes
  await page.goto('/monitore');
  await expect(page.locator('dialog.mrd')).toBeVisible();
  await page.getByRole('button', { name: 'Standard-Layout' }).click();
});

test('route via the <select> alternative, BBZ-OS locked, standard reset, profiles (#408)', async ({
  page,
}) => {
  const dialog = page.locator('dialog.mrd');
  // 6 workplace outputs + the large display
  await expect(dialog.locator('.mrd__output')).toHaveCount(7);

  const ap3 = page.getByRole('group', { name: 'Arbeitsplatzmonitor 3', exact: true });
  const ap4 = page.getByRole('group', { name: 'Arbeitsplatzmonitor 4', exact: true });

  // 1. keyboard-accessible <select> assignment (§26.14 — not drag)
  await expect(ap3.getByRole('combobox')).toHaveValue('bku3'); // migration-0042 default
  await routeVia(page, ap3, 'Coda 1');
  await expect(ap3.getByRole('combobox')).toHaveValue('coda1');

  // 2. the lower-left output is server-locked to BBZ-OS (E19-03)
  await expect(ap4.getByRole('combobox')).toBeDisabled();
  await expect(ap4.locator('.mrd__lock')).toBeVisible();

  // 3. save a profile of the current layout, 4. reset to standard
  await page.getByLabel('Profilname').fill('E2E-Nachtdienst');
  await page.getByRole('button', { name: 'Profil speichern' }).click();

  await page.getByRole('button', { name: 'Standard-Layout' }).click();
  await expect(ap3.getByRole('combobox')).toHaveValue('bku3');

  // 5. re-apply the saved profile → workplace3 back to coda1
  await page.getByLabel('Profil', { exact: true }).selectOption({ label: 'E2E-Nachtdienst' });
  await page.getByRole('button', { name: 'Anwenden' }).click();
  await expect(ap3.getByRole('combobox')).toHaveValue('coda1');

  await page.getByRole('button', { name: 'Standard-Layout' }).click();
});

test('assign an input by dragging its chip onto a monitor (#408)', async ({ page }) => {
  const ap5 = page.getByRole('group', { name: 'Arbeitsplatzmonitor 5', exact: true });
  await expect(ap5.getByRole('combobox')).toHaveValue('bku4'); // default

  const chip = page.locator('.mrd__source', { hasText: 'Coda 2' });
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/v1/monitor/routes') && r.request().method() === 'PUT',
    ),
    chip.dragTo(ap5),
  ]);
  await expect(ap5.getByRole('combobox')).toHaveValue('coda2');

  await page.getByRole('button', { name: 'Standard-Layout' }).click();
});
