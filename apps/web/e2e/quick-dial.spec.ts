import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — the quick-dial overlay (E11-15 / #225): a button opens a dialog
 * listing quick-dial contacts (E14-06) instead of a permanent grid in the
 * layout; choosing one dials it.
 *
 * `POST /calls/dial` only queues the command on the provider — the resulting
 * `calls` row appears once its `CALL_RINGING` event is ingested, and nothing
 * drains an *outbound* dial's events today (see `bbz_core/api/v1/calls.py`'s
 * `dial()` docstring and `telephony.spec.ts`'s module note on the mock event-
 * pump gap) — that's a separate, already-flagged gap, not part of #225's own
 * scope. So this asserts what #225's own AC actually promises ("Wahl startet
 * Anruf" — the command is accepted), not a full call-becomes-active UI state.
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

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

test('quick-dial overlay opens, lists a contact, and dials it (#225)', async ({ page }) => {
  await login(page);

  // no permanent grid in the layout — the overlay (a native <dialog>) takes
  // no layout space until opened
  await expect(page.locator('.qd')).toBeHidden();

  await page.getByRole('button', { name: 'Kurzwahl öffnen' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: 'Kurzwahl' });
  await expect(dialog).toBeVisible();

  const entry = dialog.getByRole('button', { name: /Pförtner Haupttor/ });
  await expect(entry).toBeVisible();

  // keyboard-operable (AC): reach and activate the entry without a mouse
  await entry.focus();
  await page.keyboard.press('Enter');

  await expect(dialog).toBeHidden();
  await expect(page.locator('.comms__error')).toHaveCount(0);
});

test('cancel closes the overlay without dialing', async ({ page }) => {
  await login(page);

  await page.getByRole('button', { name: 'Kurzwahl öffnen' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: 'Kurzwahl' });
  await expect(dialog).toBeVisible();

  await dialog.getByRole('button', { name: 'Schließen' }).click();
  await expect(dialog).toBeHidden();
});
