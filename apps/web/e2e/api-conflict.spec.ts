import { expect, test, type Locator, type Page } from '@playwright/test';

/**
 * E2E — the API client's 409 handling (E07-04 / #99). `apiClient.ts` already
 * types a 409 as `ConflictError` and every write-capable panel catches it
 * with a user-visible message, never a silent overwrite — this was only
 * ever exercised by vitest with a mocked response. Here two browser
 * contexts race a real backend: one completes a workflow step, the other
 * (still showing the now-stale "active" view) tries to complete the same
 * step again and must see the conflict message, not a silent no-op.
 * Backend behaviour: `server/tests/test_workflow_instance_api.py::
 * test_completing_a_step_out_of_order_is_a_conflict`.
 *
 * Fixture: `server/scripts/seed_e2e.py` — `BMA Gleis 5 — E2E-Konflikt`
 * (already `open`, the `e2e-bma` workflow already running).
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

function completeStepBtn(panel: Locator): Locator {
  return panel
    .locator('.wf__step--active')
    .filter({ hasText: 'Vor Ort prüfen' })
    .getByRole('button', { name: 'Schritt abschließen' });
}

test('completing an already-completed step surfaces a conflict, never a silent no-op (#99)', async ({
  browser,
  request,
  baseURL,
}) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');

  // two independent sessions viewing the same event, both mid-load before
  // either of them acts — the second stays on its now-stale snapshot.
  const [ctxA, ctxB] = await Promise.all([browser.newContext(), browser.newContext()]);
  const [pageA, pageB] = await Promise.all([ctxA.newPage(), ctxB.newPage()]);
  await Promise.all([login(pageA), login(pageB)]);
  const [panelA, panelB] = await Promise.all([
    openEvent(pageA, TITLE),
    openEvent(pageB, TITLE),
  ]);

  await completeStepBtn(panelA).click();
  await expect(panelA.locator('.wf__prog')).toHaveText('1/1');

  // B never reloaded — its step is still rendered "active" with a live
  // button; the click must reach the server and come back a 409, not just
  // vanish or silently do nothing.
  await completeStepBtn(panelB).click();
  await expect(panelB.getByRole('alert')).toContainText('geändert');
  // and the panel recovers — a follow-up load() reflects the real state
  await expect(panelB.locator('.wf__prog')).toHaveText('1/1');

  await ctxA.close();
  await ctxB.close();
});
