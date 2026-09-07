import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — SIP gateway admin (E13-07 / #281, ADR-0033). `/admin/telefonie`:
 * point BBZ at an Asterisk, store the ARI password write-only, manage the SIP
 * lines, probe the connection. The `sip_gateway` row is a migration-seeded
 * singleton, so this spec configures it and resets it in `afterEach` — no
 * per-test seed, and it must not leave state for the other specs.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const HOST = 'e2e-pbx.bbz.internal';
const LINE = '9001';

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
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Administration' }).click();
  await page.locator('.admin__nav').getByRole('link', { name: 'Telefonie / SIP' }).click();
  await expect(page).toHaveURL(/\/admin\/telefonie$/);
});

test.afterEach(async ({ page }) => {
  // disable the gateway and drop the test line so the next spec starts clean
  const csrf = (await page.context().cookies()).find((c) => c.name === 'bbz_csrf')?.value;
  if (!csrf) return;
  const headers = { 'x-csrf-token': csrf };
  await page.request
    .put('/api/v1/admin/telephony/sip', {
      headers,
      data: {
        host: '',
        port: 8088,
        tls: true,
        app_name: 'bbz-sip',
        dtmf_transport: 'rfc2833',
        ari_username: '',
        enabled: false,
      },
    })
    .catch(() => null);
  await page.request
    .delete(`/api/v1/admin/telephony/sip/lines/${LINE}`, { headers })
    .catch(() => null);
});

test('configure the gateway, persist it, add a line, probe the connection (#281)', async ({
  page,
}) => {
  const form = page.locator('form.card').first();
  await page.locator('#sip-host').fill(HOST);
  await page.locator('#sip-user').fill('bbz');
  await page.locator('#sip-pass').fill('e2e-ari-secret');
  await page.locator('.sip__check', { hasText: 'Aktiv' }).locator('input').check();
  await form.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.locator('.sip__ok')).toBeVisible();

  // reload — the host round-trips, the password does not (write-only)
  await page.reload();
  await expect(page.locator('#sip-host')).toHaveValue(HOST);
  await expect(page.locator('#sip-pass')).toHaveValue('');
  await expect(page.locator('#sip-pass')).toHaveAttribute('placeholder', /Passwort gesetzt/);

  // add a SIP line — it appears in the table with the default endpoint
  await page.locator('.sip__add input').first().fill(LINE);
  await page.locator('.sip__add').getByRole('button', { name: 'Leitung hinzufügen' }).click();
  const row = page.locator('.sip__table tbody tr', { hasText: LINE });
  await expect(row).toBeVisible();
  await expect(row.locator('code')).toHaveText(`PJSIP/${LINE}`);

  // "test connection" runs and renders a result (unreachable — no Asterisk in CI)
  await page.getByRole('button', { name: 'Verbindung testen' }).click();
  await expect(page.locator('.sip__actions .tag')).toBeVisible();
  await expect(page.locator('.sip__actions .tag')).toContainText('nicht erreichbar');
});
