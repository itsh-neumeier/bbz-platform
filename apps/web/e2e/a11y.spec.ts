import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

/**
 * E2E — accessibility baseline (E07-15 / #121, `.ai/RULES.md`: "Accessibility is
 * a functional requirement"). `eslint-plugin-vuejs-accessibility` already blocks
 * the build on lint violations; this adds the runtime `axe` scan the AC asks for
 * on Arbeitsplatz / Ereignisse / Wetterlage / Telefonbuch — no `critical` or
 * `serious` WCAG 2 A/AA violation, in both light and dark. Telefonbuch also
 * covers the contact-priority badge's AA contrast (E14-08 / #299).
 *
 * Fixtures: `server/scripts/seed_e2e.py`. Skipped when no backend answers
 * `/api/v1/meta`.
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

const PAGES = [
  { name: 'Arbeitsplatz', nav: null, ready: '.wp__store' },
  { name: 'Ereignisse', nav: 'Ereignisse', ready: '.events .detail-grid' },
  { name: 'Wetterlage', nav: 'Wetterlage', ready: '.wx' },
  { name: 'Telefonbuch', nav: 'Telefonbuch', ready: '.pb__row' },
] as const;

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(USER);
  await page.getByLabel('Passwort').fill(PASS);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/arbeitsplatz$/);
}

test.beforeEach(async ({ request, baseURL }) => {
  const r = await request.get(`${baseURL}/api/v1/meta`).catch(() => null);
  test.skip(!r || !r.ok(), 'no backend on the dev proxy');
});

for (const scheme of ['light', 'dark'] as const) {
  for (const p of PAGES) {
    test(`no serious axe violations on ${p.name} (${scheme}, #121)`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await login(page);
      if (p.nav) {
        await page.locator('.sidebar__nav').getByRole('link', { name: p.nav }).click();
      }
      await expect(page.locator(p.ready).first()).toBeVisible();

      const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze();
      const blocking = violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious',
      );
      expect(
        blocking,
        blocking.map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.length}×)`).join('\n'),
      ).toEqual([]);
    });
  }
}
