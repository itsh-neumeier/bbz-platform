import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — EPK-canvas editor (E07-19 / #129): real EPK notation on the admin
 * canvas (hexagon event / rounded-rect function / connector circle with its
 * ∧/∨/⊕ glyph) and the keyboard alternative for node positioning (AC: "jede
 * Editoraktion ist ohne Maus möglich"). Pointer-drag itself is exercised by
 * the pure `applyNodeDrag`/`snap` unit tests (`tests/workflows.spec.ts`) —
 * jsdom cannot lay out SVG, so the keyboard path is what runs end-to-end here,
 * against a real browser where `boundingBox()` reflects the actual layout.
 *
 * Fixture: `server/scripts/seed_e2e.py` — the draft template `e2e-epk`
 * (event -> XOR-split -> two functions -> XOR-join -> event).
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
  await page.locator('.sidebar__nav').getByRole('link', { name: 'Administration' }).click();
  await page.getByRole('link', { name: 'Handlungsanweisungen' }).click();
  await expect(page).toHaveURL(/\/admin\/handlungsanweisungen$/);
  await page.getByRole('button', { name: 'E2E EPK' }).click();
  await expect(page.locator('.wfp__node')).toHaveCount(6);
});

test('renders real EPK notation — hexagon events, rounded-rect functions, XOR connectors', async ({
  page,
}) => {
  await expect(page.locator('.wfp__node--event polygon')).toHaveCount(2);
  await expect(page.locator('.wfp__node--function rect')).toHaveCount(2);
  await expect(page.locator('.wfp__node--connector circle')).toHaveCount(2);
  await expect(page.locator('.wfp__glyph')).toHaveText(['⊕', '⊕']); // both connectors are XOR
});

test('a node moves with the keyboard alone and the new position survives a reload', async ({
  page,
}) => {
  const node = page.getByRole('button', { name: 'Funktion: Vor Ort prüfen' });
  const before = await node.boundingBox();
  expect(before).not.toBeNull();

  await node.focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowDown');

  const moved = await node.boundingBox();
  expect(moved).not.toBeNull();
  expect(moved!.y - before!.y).toBeGreaterThan(30); // 3 x GRID(16)px, minus AA slack

  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('status')).toContainText('gespeichert');

  await page.reload();
  await page.getByRole('button', { name: 'E2E EPK' }).click();
  const afterReload = await page
    .getByRole('button', { name: 'Funktion: Vor Ort prüfen' })
    .boundingBox();
  expect(afterReload).not.toBeNull();
  expect(Math.abs(afterReload!.y - moved!.y)).toBeLessThan(2);
});
