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
  // create — only the create form's "Name"/"Rufnummer" are on screen here,
  // nothing is selected yet
  await page.getByRole('button', { name: 'Neuer Kontakt' }).click();
  await page.getByLabel('Name', { exact: true }).fill(NAME);
  await page.getByLabel('Rufnummer', { exact: true }).fill('030987654');
  await page.getByRole('button', { name: 'Anlegen' }).click();

  const row = page.locator('.pb__row').filter({ hasText: NAME });
  await expect(row).toBeVisible();
  // no priority dot yet — a fresh contact has none
  await expect(row.locator('.pb__prio')).toHaveCount(0);

  // live search narrows the list down to just this contact (debounced, no submit)
  await page.getByLabel('Suche').fill(NAME);
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
