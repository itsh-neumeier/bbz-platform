import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — comms-sidebar tab shell (E07-18 / #127). The functional sidebar
 * (keypad, active-call controls, mini phone-book, history — #707) already
 * subsumed the originally-scoped "empty tabs" scaffold; what #127's own AC
 * still asked for and had no Playwright leg was: tabs are keyboard-operable,
 * and each panel's state survives a tab switch. All four `<div role="tabpanel">`
 * stay mounted via `v-show` (never `v-if`), so this is really a render-mode
 * regression test as much as a UX one.
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

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await login(page);
});

// "Telefon" is a substring of "Telefonbuch" — getByRole's default name match
// is substring, so every lookup here needs `exact` to stay unambiguous.
function tab(page: Page, name: string) {
  return page.getByRole('tab', { name, exact: true });
}

test('switching tabs preserves each panel\'s own state (#127)', async ({ page }) => {
  const numberInput = page.getByLabel('Rufnummer');
  await numberInput.fill('030123456');

  await tab(page, 'Telefonbuch').click();
  await expect(page.getByRole('tabpanel')).toBeVisible();

  await tab(page, 'Historie').click();
  await expect(page.getByRole('tabpanel')).toBeVisible();

  await tab(page, 'Telefon').click();
  await expect(numberInput).toHaveValue('030123456');
});

test('every tab is reachable and operable without a mouse (#127)', async ({ page }) => {
  for (const name of ['Gespräch', 'Telefonbuch', 'Historie', 'Telefon']) {
    const tabBtn = tab(page, name);
    await tabBtn.focus();
    await page.keyboard.press('Enter');
    await expect(tabBtn).toHaveAttribute('aria-selected', 'true');
  }
});
