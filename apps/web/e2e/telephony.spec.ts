import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — the telephony comms sidebar's real call flow (E11-13/14, #221/#223):
 * an incoming mock call appears, gets answered, its duration ticks live, and
 * hanging up without a documentation category opens the mandatory popup
 * instead of silently closing the call.
 *
 * No background worker drains a telephony provider's event stream today (see
 * `bbz_core/api/v1/telephony.py`'s module docstring) — a call never becomes
 * visible via `GET /calls/ringing` no matter how it started. This drives the
 * mock provider's own `simulate_incoming()` scenario helper directly via
 * `POST /telephony/_mock/simulate-incoming` (`calls.simulate_mock_scenario`,
 * granted to the E2E `admin` user in `seed_e2e.py`), exactly what a real CTI
 * gateway's webhook would otherwise deliver.
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

async function simulateIncoming(page: Page, baseURL: string): Promise<void> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === 'bbz_csrf')?.value ?? '';
  const res = await page.request.post(`${baseURL}/api/v1/telephony/_mock/simulate-incoming`, {
    headers: { 'x-csrf-token': csrf, 'x-command-id': crypto.randomUUID() },
    data: { from_number: '+49911500', to_line: '1001', display_name: 'EVU Nord' },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

test('incoming call → answer → live duration → hangup gated on documentation (#221/#223)', async ({
  page,
  baseURL,
}) => {
  // longer than the 30 s default: login (cold Argon2) + a real simulate-incoming
  // round trip + waiting out an actual duration tick (>=1 s, up to 5 s) + the
  // doc-save-then-hangup pair chain more real backend round trips than a
  // typical spec here — a first isolated run genuinely reached the final
  // assertion at the 30 s mark rather than hanging, so this is headroom, not
  // a mask for a real slowdown.
  test.setTimeout(60_000);

  await login(page);
  await simulateIncoming(page, baseURL!);

  // Telefon tab — the waiting call appears (SSE-nudged refresh). `.last()`:
  // a retried attempt leaves its own simulated call behind too, so always
  // act on the one just created.
  const waiting = page.locator('.wq__item').filter({ hasText: 'EVU Nord' }).last();
  await expect(waiting).toBeVisible();

  await waiting.getByRole('button', { name: 'Annehmen' }).click();

  // Gespräch tab opens automatically; the duration ticks
  const duration = page.locator('.ac__duration');
  await expect(duration).toHaveText(/^\d+:\d{2}$/);
  const first = await duration.textContent();
  await expect(duration).not.toHaveText(first ?? '', { timeout: 5_000 });

  // hangup without a category must NOT silently end the call — the popup
  // gates it
  await page.getByRole('button', { name: 'Auflegen' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Dokumentation erforderlich' })).toBeVisible();
  await expect(dialog.getByRole('button', { name: /Kategorie speichern/ })).toBeDisabled();

  await dialog.getByRole('radio').first().check();
  await dialog.getByRole('button', { name: /Kategorie speichern/ }).click();

  // the popup closes and the call is genuinely gone — not a silent no-op
  await expect(dialog).toBeHidden();
  await expect(page.getByText('Kein aktives Gespräch.')).toBeVisible();
});
