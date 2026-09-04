import { expect, test, type Locator, type Page } from '@playwright/test';

/**
 * E2E — the API client's 409 handling (E07-04 / #99). `apiClient.ts` already
 * types a 409 as `ConflictError`, and every write-capable panel catches it
 * with a user-visible message, never a silent overwrite — this was only
 * ever exercised by vitest against a mocked response. Here two browser
 * contexts race a real backend: both open the same event, both fire the
 * *same* next lifecycle action (e.g. "Annehmen") at once. Exactly one can
 * win; the other's request still carries the version it loaded before
 * either tab acted, so the server rejects it — `stores/events.ts`
 * `transition()` reloads on a `ConflictError`, `EventActions.vue` shows
 * `event.conflict`. Server-side: `EventRepository.save(expected_version=…)`
 * / `InvalidTransition` → `ConflictError` (`bbz_core/api/v1/events.py`).
 *
 * Retry-safe by construction: it races whichever action is *currently*
 * enabled rather than assuming a fixed starting status, so a retry (which
 * reuses the same seeded event, now one step further along) still has a
 * next action to race, up to all 4 lifecycle steps.
 *
 * Fixture: `server/scripts/seed_e2e.py` — `BMA Gleis 5 — E2E-Konflikt`
 * (fresh, `new`).
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
const TITLE = 'BMA Gleis 5 — E2E-Konflikt';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

/** Click the Ereignisspeicher row carrying `title`; resolve to its processing panel. */
async function openEvent(page: Page, title: string): Promise<Locator> {
  const row = page.locator('.wp__row').filter({ hasText: title });
  await expect(row).toBeVisible();
  await row.click();
  const panel = page.locator('.epp');
  await expect(panel.getByRole('heading', { name: title })).toBeVisible();
  return panel;
}

/** Whichever of the 4 always-rendered lifecycle buttons is valid for the
 *  event's current status — exactly one is enabled at a time. */
function nextActionButton(panel: Locator): Locator {
  return panel.locator('.epp__actions button:not([disabled])');
}

test('two tabs racing the same lifecycle action: one wins, the other gets a real conflict (#99)', async ({
  browser,
  request,
  baseURL,
}) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');

  const [ctxA, ctxB] = await Promise.all([browser.newContext(), browser.newContext()]);
  const [pageA, pageB] = await Promise.all([ctxA.newPage(), ctxB.newPage()]);
  await Promise.all([login(pageA), login(pageB)]);
  const [panelA, panelB] = await Promise.all([openEvent(pageA, TITLE), openEvent(pageB, TITLE)]);

  // fire the same action from both tabs at once — both hold the same
  // pre-action version, so this is a genuine race, not a scripted sequence.
  await Promise.all([nextActionButton(panelA).click(), nextActionButton(panelB).click()]);

  // exactly one side must show the conflict message — never neither (a
  // silent double no-op) and never both (the server rejecting the winner too).
  await expect
    .poll(
      async () => {
        const [a, b] = await Promise.all([
          panelA.locator('.acts__conflict').isVisible(),
          panelB.locator('.acts__conflict').isVisible(),
        ]);
        return Number(a) + Number(b);
      },
      { timeout: 10_000 },
    )
    .toBe(1);

  // and both views converge back on the one real, single status change —
  // the loser's panel reloads via the conflict handler, not a stale guess.
  const statusA = await panelA.locator('.epp__status').textContent();
  await expect(panelB.locator('.epp__status')).toHaveText(statusA ?? '');

  await ctxA.close();
  await ctxB.close();
});
