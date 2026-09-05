import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — contact ↔ call-history link (E14-10 / #303, MASTER_PROMPT §13.8/§13.9).
 * A call from a known contact appears in that contact's history in the
 * phone-book (with "letzter Kontakt"), and from the comms sidebar's Historie
 * tab the resolved caller links back to the contact.
 *
 * Same mock event-pump note as `telephony.spec.ts`. Seeded contact
 * (`server/scripts/seed_e2e.py`): "Streckenposten Nord", +4991166666.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const CONTACT = 'Streckenposten Nord';
const NUMBER = '+4991166666';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

/** run one full inbound call from NUMBER → answered, documented, closed, so
 *  it lands in the history with its `caller_contact_id` resolved. */
async function completeOneCall(page: Page, baseURL: string): Promise<void> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === 'bbz_csrf')?.value ?? '';
  const hdr = () => ({ 'x-csrf-token': csrf, 'x-command-id': crypto.randomUUID() });

  const sim = await page.request.post(`${baseURL}/api/v1/telephony/_mock/simulate-incoming`, {
    headers: hdr(),
    data: { from_number: NUMBER, to_line: '1001', display_name: CONTACT },
  });
  expect(sim.ok(), await sim.text()).toBeTruthy();

  const ringing = await (await page.request.get(`${baseURL}/api/v1/calls/ringing`)).json();
  const call = (ringing.items as { id: string; participants: { number: string }[] }[])
    .filter((c) => c.participants.some((p) => p.number === NUMBER))
    .at(-1)!;
  expect(call).toBeTruthy();

  await page.request.post(`${baseURL}/api/v1/calls/${call.id}/answer`, { headers: hdr() });
  await page.request.post(`${baseURL}/api/v1/calls/${call.id}/hangup`, { headers: hdr() });
  await page.request.put(`${baseURL}/api/v1/calls/${call.id}/documentation`, {
    headers: hdr(),
    data: { category: 'technical_fault', free_text: null },
  });
}

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

test('contact → its call history, and history → the contact (#303)', async ({ page, baseURL }) => {
  test.setTimeout(60_000);
  await login(page);
  await completeOneCall(page, baseURL!);

  // direction 1: phone-book → the contact's own call history
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Telefonbuch' }).click();
  await expect(page).toHaveURL(/\/telefonbuch$/);
  await page.getByRole('button', { name: new RegExp(CONTACT) }).click();
  const detail = page.locator('.pb__detail');
  await expect(detail.locator('.pb__lastcontact')).toContainText('Letzter Kontakt');
  await expect(detail.locator('.pb__histrow').first()).toContainText('Technische Störung');

  // direction 2: comms sidebar Historie tab → link back to the contact
  await page.getByRole('tab', { name: 'Historie', exact: true }).click();
  const link = page
    .locator('.hist__item')
    .filter({ hasText: CONTACT })
    .getByRole('link')
    .first();
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(/\/telefonbuch\?contact=/);
  await expect(page.locator('.pb__detail')).toContainText(CONTACT);
});
