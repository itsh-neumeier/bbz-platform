import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — phone-book CRUD (E14-07 / #297). `PhonebookPage.vue` already has full
 * CRUD, live search and priority assignment, all permission-gated — this was
 * only ever exercised by vitest (`PhonebookPage.spec.ts`) against a mocked
 * API. The issue's own Tests field asks for exactly this walk: "Kontakt
 * anlegen, suchen, Priorität setzen."
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const NAME = 'E2E Telefonbuch-Kontakt';
// the server requires E.164 (`^\+[1-9][0-9]{1,14}$`) — a bare national-format
// number 422s, silently (the create form has no client-side pattern check)
const NUMBER = '+4930987654';

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
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Telefonbuch' }).click();
  await expect(page).toHaveURL(/\/telefonbuch$/);
});

test('create a contact, find it by live search, then set its call priority (#297)', async ({
  page,
}) => {
  // create — by #id, not label text: the persistent comms sidebar (every
  // route) has its own "Rufnummer"/search-ish labels that collide with the
  // phonebook page's, both as exact matches and as getByLabel substrings
  // ("Suche" ⊂ "Kontakt suchen").
  await page.getByRole('button', { name: 'Neuer Kontakt' }).click();
  const createForm = page.locator('.pb__create');
  await createForm.locator('#pb-n-name').fill(NAME);
  await createForm.locator('#pb-n-num').fill(NUMBER);
  await createForm.getByRole('button', { name: 'Anlegen' }).click();

  await expect(page.locator('.pb__error')).toHaveCount(0);
  const row = page.locator('.pb__row').filter({ hasText: NAME });
  await expect(row).toBeVisible();
  // no priority dot yet — a fresh contact has none
  await expect(row.locator('.pb__prio')).toHaveCount(0);

  // live search narrows the list down to just this contact (debounced, no submit)
  await page.locator('#pb-q').fill(NAME);
  await expect(page.locator('.pb__row')).toHaveCount(1);
  await expect(row).toBeVisible();

  // the detail panel opened on create (createContact selects the new row) —
  // set its call priority to "hoch"
  const detail = page.locator('.pb__detail');
  await detail.getByRole('button', { name: 'hoch' }).click();
  await expect(detail.getByRole('button', { name: 'hoch' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(row.locator('.pb__prio')).toHaveClass(/prio--high/);
});
