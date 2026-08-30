import { expect, test } from '@playwright/test';

/**
 * Mandatory E2E — archive / post-processing lifecycle (roadmap E20-08,
 * MASTER_PROMPT §24 steps 8–10 / §13.6).
 *
 * The backend flow is fully covered now by
 * `server/tests/test_e2e_archive_lifecycle.py`. This browser script is the
 * UI half and is `test.fixme` until the screens it drives exist:
 *   - archive view + post-processing notes  — E07-11 (#113)
 *   - reactivation confirmation dialog       — E07-12 (#115)
 *
 * When those land, remove `.fixme` and flesh out the selectors. The steps:
 *   1. operator opens an archived event from `/archive`
 *   2. the detail shows the full history (status, notes, workflow, audit refs)
 *   3. add a post-processing note, then edit it — the previous version stays
 *   4. export the event → a bundle download / view, with audit entries
 *   5. reactivate → the confirmation dialog requires a reason + explicit confirm
 *   6. the event is back in the active queue; nothing was deleted
 */
test.fixme('archive → detail → post-processing note → export → reactivation', async ({ page }) => {
  await page.goto('/archive');

  // 1–2. open an archived event and see its full detail
  await page.getByRole('link', { name: /Brandmeldeanlage/ }).first().click();
  await expect(page.getByText(/archiviert/i)).toBeVisible();
  await expect(page.getByRole('region', { name: /Verlauf|History/i })).toBeVisible();

  // 3. post-processing note: add then edit, old version preserved
  await page.getByRole('button', { name: /Nachbearbeitungsnotiz/i }).click();
  await page.getByRole('textbox', { name: /Notiz/i }).fill('Nachbericht v1');
  await page.getByRole('button', { name: /Speichern/i }).click();
  await page.getByRole('button', { name: /Bearbeiten/i }).click();
  await page.getByRole('textbox', { name: /Notiz/i }).fill('Nachbericht v2');
  await page.getByRole('button', { name: /Speichern/i }).click();
  await expect(page.getByText('Nachbericht v2')).toBeVisible();
  await expect(page.getByText(/Version 1|v1/)).toBeVisible();

  // 4. export
  await page.getByRole('button', { name: /Export/i }).click();
  await expect(page.getByText(/EVENT_ARCHIVED/)).toBeVisible();

  // 5. reactivation requires confirm + reason
  await page.getByRole('button', { name: /Reaktivieren/i }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: /Bestätigen/i }).click();
  await expect(dialog.getByText(/Grund/i)).toBeVisible(); // rejected without a reason
  await dialog.getByRole('textbox', { name: /Grund/i }).fill('Rückfrage Kripo');
  await dialog.getByRole('checkbox', { name: /bestätige/i }).check();
  await dialog.getByRole('button', { name: /Bestätigen/i }).click();

  // 6. back in the active queue
  await page.goto('/queue');
  await expect(page.getByRole('link', { name: /Brandmeldeanlage/ })).toBeVisible();
});
