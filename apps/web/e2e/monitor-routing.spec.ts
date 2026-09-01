import { expect, test } from '@playwright/test';

/**
 * Mandatory E2E — monitor / KVM routing (roadmap E19-10, MASTER_PROMPT §9).
 *
 * The backend flow is fully covered by
 * `server/tests/test_e2e_monitor_routing.py` (API level, against `monitor_mock`).
 * This browser script is the UI half and is `test.fixme` until the screen it
 * drives exists:
 *   - the monitor-routing dialog (3×2 grid + large display, drag & drop AND a
 *     keyboard / select alternative, standard-layout button, profile save/load,
 *     the lower-left field shown locked) — E19-08 (#408)
 *
 * When it lands, remove `.fixme` and flesh out the selectors. The four scenarios:
 *   1. change a route (drag an input onto an output, or pick it via the select
 *      alternative) → the change is reflected and persisted
 *   2. the lower-left output is shown locked to BBZ-OS and cannot be changed
 *      (UI + server both refuse)
 *   3. save the current layout as a profile, then apply it again later
 *   4. "standard layout" button restores the documented default
 */
test.fixme('monitor routing — route, fixed rule, profile save/apply, reset', async ({ page }) => {
  await page.goto('/monitor');
  await page.getByRole('button', { name: /Monitor-Layout|Monitorrouting/i }).click();

  // 1. change a route via the keyboard / select alternative (must not depend on
  //    drag & drop — §26.14)
  const ap3 = page.getByRole('group', { name: /Arbeitsplatzmonitor 3/i });
  await ap3.getByRole('combobox').selectOption({ label: /Coda 1/i });
  await expect(ap3.getByText(/Coda 1/i)).toBeVisible();

  // 2. the lower-left field is locked to BBZ-OS
  const lowerLeft = page.getByRole('group', { name: /unten links|Arbeitsplatzmonitor 4/i });
  await expect(lowerLeft.getByText(/BBZ-OS/i)).toBeVisible();
  await expect(lowerLeft.getByRole('combobox')).toBeDisabled();

  // 3. save as a profile, then apply it
  await page.getByRole('button', { name: /Profil speichern/i }).click();
  await page.getByLabel(/Name/i).fill('Nachtdienst');
  await page.getByRole('button', { name: /Speichern/i }).click();
  await page.getByRole('button', { name: /Standard-Layout/i }).click();
  await page.getByRole('combobox', { name: /Profil/i }).selectOption({ label: 'Nachtdienst' });
  await page.getByRole('button', { name: /Anwenden/i }).click();
  await expect(ap3.getByText(/Coda 1/i)).toBeVisible();

  // 4. standard layout button
  await page.getByRole('button', { name: /Standard-Layout/i }).click();
  await expect(lowerLeft.getByText(/BBZ-OS/i)).toBeVisible();
});
