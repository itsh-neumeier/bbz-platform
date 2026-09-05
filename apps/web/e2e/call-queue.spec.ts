import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — the waiting-call queue's priority behaviour (E14-09 / #301,
 * MASTER_PROMPT §13.9): sorted high→low regardless of arrival order, a graded
 * background pulse (high hardest, medium fainter, low none), `prefers-reduced-
 * motion` stills it, and an unknown caller still shows its number.
 *
 * Same mock event-pump note as `telephony.spec.ts` — drives the mock's
 * `simulate-incoming` scenario endpoint directly. Seeded priority contacts
 * (`server/scripts/seed_e2e.py`): Feuerleitzentrale=high, Netzleitstelle
 * Ost=medium, Info-Punkt Halle=low; a 4th number matches no contact = unknown.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

const CALLS = {
  high: { number: '+4991150099', name: 'Feuerleitzentrale' },
  medium: { number: '+4991150098', name: 'Netzleitstelle Ost' },
  low: { number: '+4991150097', name: 'Info-Punkt Halle' },
  unknown: { number: '+4999888777', name: '+4999888777' },
} as const;

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

async function simulate(page: Page, baseURL: string, from: string, name: string): Promise<void> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === 'bbz_csrf')?.value ?? '';
  const res = await page.request.post(`${baseURL}/api/v1/telephony/_mock/simulate-incoming`, {
    headers: { 'x-csrf-token': csrf, 'x-command-id': crypto.randomUUID() },
    data: { from_number: from, to_line: '1001', display_name: name },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

/** the keyframe name applied to the `.wq__item` that shows `text` (`.last()`:
 *  a shared dev DB may hold an older call from the same caller). */
function animationName(page: Page, text: string): Promise<string> {
  return page
    .locator('.wq__item')
    .filter({ hasText: text })
    .last()
    .evaluate((el) => getComputedStyle(el).animationName);
}

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

// this spec's whole point is a *full* ringing queue, and the suite shares one
// seeded DB (workers:1) — leave none behind, or the specs that run after us
// inherit them: an unanswered call gives the Telefon tab a count badge (breaks
// `getByRole('tab', {name: 'Telefon', exact: true})`), and a merely-hung-up
// call sits in `ended_pending_documentation`, which is a LIVE_STATE the calls
// store treats as "the active call". So fully close each: hang up *then*
// document it (category → `CALL_ENDED`, state `disconnected`, gone for good).
test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === 'skipped') return;
  const cookies = await page.context().cookies().catch(() => []);
  const csrf = cookies.find((c) => c.name === 'bbz_csrf')?.value ?? '';
  if (!csrf) return;
  const hdr = { 'x-csrf-token': csrf, 'x-command-id': crypto.randomUUID() };
  const res = await page.request.get('/api/v1/calls/ringing').catch(() => null);
  if (!res || !res.ok()) return;
  const { items } = (await res.json()) as { items: { id: string }[] };
  for (const c of items) {
    await page.request
      .post(`/api/v1/calls/${c.id}/hangup`, { headers: { ...hdr, 'x-command-id': crypto.randomUUID() } })
      .catch(() => undefined);
    await page.request
      .put(`/api/v1/calls/${c.id}/documentation`, {
        headers: { ...hdr, 'x-command-id': crypto.randomUUID() },
        data: { category: 'other', free_text: null },
      })
      .catch(() => undefined);
  }
});

test('queue sorts high→low, animates by priority, shows unknown callers (#301)', async ({
  page,
  baseURL,
}) => {
  test.setTimeout(60_000);
  await login(page);

  // arrive scrambled — sort must not depend on arrival order
  await simulate(page, baseURL!, CALLS.low.number, CALLS.low.name);
  await simulate(page, baseURL!, CALLS.unknown.number, CALLS.unknown.name);
  await simulate(page, baseURL!, CALLS.high.number, CALLS.high.name);
  await simulate(page, baseURL!, CALLS.medium.number, CALLS.medium.name);

  // all four are in the queue (a shared dev DB may hold other calls too, so
  // assert on our own, by name, not an exact total count)
  const row = (name: string) => page.locator('.wq__item').filter({ hasText: name }).last();
  for (const c of Object.values(CALLS)) await expect(row(c.name)).toBeVisible();

  // sorted high → medium → low → unknown: compare the four rows' vertical order
  const yOf = (name: string) =>
    row(name)
      .boundingBox()
      .then((b) => b!.y);
  const [yHigh, yMedium, yLow, yUnknown] = await Promise.all([
    yOf(CALLS.high.name),
    yOf(CALLS.medium.name),
    yOf(CALLS.low.name),
    yOf(CALLS.unknown.name),
  ]);
  expect(yHigh).toBeLessThan(yMedium);
  expect(yMedium).toBeLessThan(yLow);
  expect(yLow).toBeLessThan(yUnknown);

  // unknown caller: its number is shown, and it carries no priority label
  await expect(row(CALLS.unknown.name)).toContainText('+4999888777');
  await expect(row(CALLS.unknown.name).locator('.wq__prio')).toHaveCount(0);

  // graded animation: high pulses, medium pulses (a different keyframe), low
  // none. Vue's <style scoped> suffixes @keyframes names with a scope hash,
  // so match the prefix, not the exact name.
  expect(await animationName(page, CALLS.high.name)).toMatch(/^wq-pulse-high\b/);
  expect(await animationName(page, CALLS.medium.name)).toMatch(/^wq-pulse-medium\b/);
  expect(await animationName(page, CALLS.low.name)).toBe('none');
});

test('prefers-reduced-motion stills the queue pulse but keeps it readable (#301)', async ({
  page,
  baseURL,
}) => {
  test.setTimeout(60_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await login(page);

  await simulate(page, baseURL!, CALLS.high.number, CALLS.high.name);
  const item = page.locator('.wq__item').filter({ hasText: CALLS.high.name }).first();
  await expect(item).toBeVisible();

  // no animation…
  expect(await animationName(page, CALLS.high.name)).toBe('none');
  // …but the priority is still conveyed: the colour stripe + the text label
  await expect(item.locator('.wq__prio')).toHaveText('hoch');
});
