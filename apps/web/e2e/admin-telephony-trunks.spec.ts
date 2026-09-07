import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — SIP trunks (ITSP) admin (E13-09 / #803, ADR-0034). `/admin/telefonie`
 * → "SIP-Trunks": create a trunk from the LEONET preset, add a public number,
 * and check the generated Asterisk config carries the sections. The trunk +
 * number are removed in `afterEach` so no state leaks to the other specs.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const TRUNK = 'e2e-leonet';
const NUMBER = '+499115550001';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

test.beforeEach(async ({ request, baseURL, page }, testInfo) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');

  // login (cold Argon2) + first visit to /admin/telefonie (a dev server compiles
  // the route chunk on demand) can together exceed the 30 s default.
  testInfo.setTimeout(90_000);
  await login(page);
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Administration' }).click();
  const loaded = page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/admin/telephony/sip/trunks') && res.request().method() === 'GET',
  );
  await page.locator('.admin__nav').getByRole('link', { name: 'Telefonie / SIP' }).click();
  await expect(page).toHaveURL(/\/admin\/telefonie$/);
  await loaded;
});

test.afterEach(async ({ page }) => {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'bbz_csrf')?.value;
  if (!csrf) return;
  const headers = { 'x-csrf-token': csrf };
  await page.request
    .delete(`/api/v1/admin/telephony/sip/numbers/${encodeURIComponent(NUMBER)}`, { headers })
    .catch(() => null);
  await page.request
    .delete(`/api/v1/admin/telephony/sip/trunks/${TRUNK}`, { headers })
    .catch(() => null);
});

test('create a trunk from the preset, add a number, inspect the generated config (#803)', async ({
  page,
}) => {
  // --- new trunk from the LEONET preset ---
  await page.locator('#sipt-id').fill(TRUNK);
  await page.locator('#sipt-provider').selectOption('leonet');
  await expect(page.locator('#sipt-server')).toHaveValue('sip.leovoice.online');
  await expect(page.locator('.sipt__banner--preset')).toContainText('Auftragsbestätigung');
  await page.locator('#sipt-user').fill('leo499115550001');
  await page.locator('#sipt-pass').fill('e2e-trunk-secret');
  await page.locator('.sipt__check', { hasText: 'Aktiv' }).locator('input').check();

  const saved = page.waitForResponse(
    (r) =>
      r.url().includes(`/api/v1/admin/telephony/sip/trunks/${TRUNK}`) &&
      r.request().method() === 'PUT',
  );
  await page.locator('.sipt form.card').getByRole('button', { name: 'Speichern' }).click();
  expect((await saved).status()).toBe(200);

  const row = page.locator('.sipt__table tbody tr', { hasText: TRUNK });
  await expect(row).toBeVisible();
  await expect(row).toContainText('registriert');
  await expect(row).toContainText('Passwort gesetzt');

  // --- edit → save again: the PUT body must not carry read-only fields (422) ---
  await row.getByRole('button', { name: 'Bearbeiten' }).click();
  await expect(page.locator('#sipt-id')).toBeDisabled();
  await page.locator('#sipt-name').fill('LEONET E2E');
  const resaved = page.waitForResponse(
    (r) =>
      r.url().includes(`/api/v1/admin/telephony/sip/trunks/${TRUNK}`) &&
      r.request().method() === 'PUT',
  );
  await page.locator('.sipt form.card').getByRole('button', { name: 'Speichern' }).click();
  expect((await resaved).status()).toBe(200); // not 422
  await expect(page.locator('.sipt__table tbody tr', { hasText: 'LEONET E2E' })).toBeVisible();

  // --- add a public number on the trunk ---
  const add = page.locator('.sipt__add');
  await add.locator('input').first().fill(NUMBER);
  await add.locator('select').selectOption(TRUNK);
  await add.locator('input').nth(1).fill('e2e-tor');
  await add.getByRole('button', { name: 'Rufnummer hinzufügen' }).click();
  await expect(page.locator('.sipt__table tbody tr', { hasText: NUMBER })).toBeVisible();

  // --- the generated Asterisk config carries the sections ---
  await page.getByRole('button', { name: 'Konfiguration anzeigen' }).click();
  const config = page.locator('.sipt__config');
  await expect(config).toBeVisible();
  await expect(config).toContainText(`[${TRUNK}]`);
  await expect(config).toContainText(`[from-${TRUNK}]`);
  await expect(config).toContainText('Stasis(bbz-sip,${BBZ_LINE})');
});
