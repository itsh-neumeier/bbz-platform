import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — the full §24 telephony lifecycle (E11-16 / #227): incoming → priority
 * recognized → answer → category set → free text → hangup → audit verified
 * via the API. All 7 MASTER_PROMPT §24 steps, plus the CALL_DOCUMENTED audit
 * check the roadmap's own scope calls for.
 *
 * `telephony.spec.ts` (#221/#223) already covers the narrower "hangup without
 * a category is gated by a popup" flow. This one exercises the other, equally
 * valid path: category + free text are set proactively during the call (the
 * *inline* form in the Gespräch tab, `.ac__doc`), so hangup closes the call
 * immediately with no gate needed — matching #227's own listed step order
 * ("Kategorie setzen → Freitext → auflegen", not "auflegen → Kategorie").
 *
 * Same mock event-pump caveat as `telephony.spec.ts`: nothing drains a
 * telephony provider's events on its own, so this drives the mock's
 * `simulate-incoming` scenario endpoint directly, same as that spec.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';
// seeded by server/scripts/seed_e2e.py: "Feuerleitzentrale", priority high
const CALLER_NUMBER = '+4991150099';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

function csrfHeader(page: Page): Promise<string> {
  return page
    .context()
    .cookies()
    .then((cookies) => cookies.find((c) => c.name === 'bbz_csrf')?.value ?? '');
}

async function simulateIncoming(page: Page, baseURL: string): Promise<void> {
  const res = await page.request.post(`${baseURL}/api/v1/telephony/_mock/simulate-incoming`, {
    headers: { 'x-csrf-token': await csrfHeader(page), 'x-command-id': crypto.randomUUID() },
    data: { from_number: CALLER_NUMBER, to_line: '1001', display_name: 'Feuerleitzentrale' },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

/** the internal `Call.id` — needed to filter the audit query, distinct from
 *  the provider's own `source_call_id`. Uses `page.request`, not the bare
 *  `request` fixture — the latter is a separate, cookie-less API context and
 *  isn't authenticated as the page's logged-in session. */
async function ringingCallId(page: Page, baseURL: string): Promise<string> {
  const res = await page.request.get(`${baseURL}/api/v1/calls/ringing`);
  expect(res.ok(), await res.text()).toBeTruthy();
  const body = (await res.json()) as { items: { id: string; participants: { number: string }[] }[] };
  // last, not first: a debris call from an earlier local retry (same
  // caller/priority) would sort *before* the current one (longest-wait-first
  // among equal priority) — same reasoning as the UI locator's `.last()`.
  const matches = body.items.filter((c) => c.participants.some((p) => p.number === CALLER_NUMBER));
  expect(matches.length, 'the simulated call should be in the ringing queue').toBeGreaterThan(0);
  return matches[matches.length - 1].id;
}

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

test('full telephony lifecycle: incoming → priority → answer → document → hangup → audit (#227)', async ({
  page,
  baseURL,
}) => {
  test.setTimeout(60_000);

  await login(page);
  await simulateIncoming(page, baseURL!);
  const callId = await ringingCallId(page, baseURL!);

  // 1+2: incoming, priority recognized. `.last()`: a retried attempt leaves
  // its own simulated call behind too (same reason as telephony.spec.ts).
  const waiting = page.locator('.wq__item').filter({ hasText: 'Feuerleitzentrale' }).last();
  await expect(waiting).toBeVisible();
  await expect(waiting.locator('.wq__prio')).toHaveText('hoch');

  // 3: answer
  await waiting.getByRole('button', { name: 'Annehmen' }).click();
  await expect(page.locator('.ac__who')).toBeVisible();

  // 4+5: category + free text, set proactively (the inline form, not the
  // hangup-gate popup — that's telephony.spec.ts's own flow). Wait for the
  // PUT to actually round-trip before hanging up — a bare click() only
  // waits for the DOM event, not the async save it triggers, and hangup
  // right after would otherwise race stale `docRequired` state.
  await page.locator('input[name="callcat"]').first().check();
  await page.locator('#ac-free').fill('Rückruf durch Einsatzleitung erbeten.');
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes(`/calls/${callId}/documentation`) && r.request().method() === 'PUT',
    ),
    page.getByRole('button', { name: 'Dokumentation speichern' }).click(),
  ]);
  // the "documentation required" banner clearing is the visible signal that
  // the store's reactive `docRequired` has caught up with the just-saved
  // category — also gives it a moment if it hasn't quite yet.
  await expect(page.locator('.ac__docreq')).toHaveCount(0);

  // 6: hangup — no gate popup this time, the category is already set
  await page.getByRole('button', { name: 'Auflegen' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('Kein aktives Gespräch.')).toBeVisible();

  // 7: audit verified via the API
  const auditRes = await page.request.get(
    `${baseURL}/api/v1/audit?action=CALL_DOCUMENTED&target_id=${callId}`,
  );
  expect(auditRes.ok(), await auditRes.text()).toBeTruthy();
  const audit = (await auditRes.json()) as {
    items: { after: { category: string; has_free_text: boolean } | null }[];
  };
  expect(audit.items.length).toBeGreaterThan(0);
  expect(audit.items[0].after?.has_free_text).toBe(true);
});
