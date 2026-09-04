import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — the operator event lifecycle (MASTER_PROMPT §24, roadmap E07-16 / #123).
 *
 * Drives the whole §24 walk through the Arbeitsplatz UI, including the two steps
 * that had no frontend before #109 / #111: acting on a bound workflow step, and
 * handing an event to a named operator / taking it over. Backend coverage:
 * `server/tests/test_e2e_archive_lifecycle.py`, `test_workflow_lifecycle_api.py`
 * and `test_event_assign_api.py`.
 *
 * Fixtures: `server/scripts/seed_e2e.py`. Skipped when no backend answers
 * `/api/v1/meta` (e.g. a bare `npm run e2e`).
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

const LIFECYCLE = 'BMA Halle 7 — E2E-Lebenszyklus';
const TAKEOVER = 'BMA Halle 3 — E2E-Übernahme';

test.beforeEach(async ({ request, baseURL, page }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
});

/** Click the Ereignisspeicher row carrying `title`; resolve to its processing panel. */
async function openEvent(page: Page, title: string) {
  const row = page.locator('.wp__row').filter({ hasText: title });
  await expect(row).toBeVisible();
  await row.click();
  const panel = page.locator('.epp');
  await expect(panel.getByRole('heading', { name: title })).toBeVisible();
  return panel;
}

test('lifecycle: accept → acknowledge → open → complete the workflow step → archive → reactivate', async ({
  page,
}) => {
  const panel = await openEvent(page, LIFECYCLE);
  const status = panel.locator('.epp__status');
  const act = (name: string) => panel.locator('.epp__actions').getByRole('button', { name });

  // §24 steps 2–4 — the status chip tracks every transition
  await expect(status).toHaveText('neu');
  await act('Annehmen').click();
  await expect(status).toHaveText('angenommen');
  await act('Quittieren').click();
  await expect(status).toHaveText('quittiert');
  await act('Öffnen').click();
  await expect(status).toHaveText('in Bearbeitung');

  // §24 step 6 / #109 — act on the bound workflow step (backend-only before)
  const step = panel.locator('.wf__step--active').filter({ hasText: 'Vor Ort prüfen' });
  await step.getByRole('button', { name: 'Schritt abschließen' }).click();
  await expect(panel.locator('.wf__prog')).toHaveText('1/1');

  // §24 steps 8–9 — archive, and the archived detail is still fully there
  await act('Archivieren').click();
  await expect(status).toHaveText('archiviert');
  await expect(panel.getByText('Verlauf', { exact: true })).toBeVisible();
  await expect(panel.getByText('Nachbearbeitungsnotizen')).toBeVisible();

  // §24 step 10 — reactivation is a deliberate confirm + a mandatory reason
  await panel.getByRole('button', { name: 'Reaktivieren' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'Reaktivieren bestätigen' })).toBeDisabled();
  await dialog.locator('#rd-reason').fill('Rückfrage Bundespolizei — E2E');
  await dialog.getByRole('button', { name: 'Reaktivieren bestätigen' }).click();

  await expect(page).toHaveURL(/\/ereignisse\/[0-9a-f-]{36}$/);
  await expect(page.locator('.epp__status')).toHaveText('in Bearbeitung');
});

test('ownership: take an event over from an offline colleague, then hand it back (#111)', async ({
  page,
}) => {
  const panel = await openEvent(page, TAKEOVER);
  const owner = panel.locator('.own__assignee strong');
  await expect(owner).toHaveText('andere Person');

  // the colleague never logged in → counts as offline → takeover is allowed
  await panel.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(owner).toHaveText('Sie');
  await expect(panel.getByRole('button', { name: 'Übernehmen' })).toHaveCount(0);

  // hand it to a named operator from the roster (GET /events/assignable)
  await panel.locator('.own__assign select').selectOption({ label: 'E2E Kollege' });
  await expect(owner).toHaveText('andere Person');
});
