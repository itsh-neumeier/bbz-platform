import { chromium, type FullConfig } from '@playwright/test';

/**
 * Warm everything the first spec would otherwise pay for on a cold stack: the
 * Vite module graph, the API's Argon2 initialisation, the DB pool and the
 * post-login SPA hydration. Without this the first `beforeEach` login races the
 * cold start and its button sticks on "Anmeldung läuft …".
 */
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'Wolke7-Bahnhof!x';

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? 'http://localhost:5173';
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });
  try {
    for (let attempt = 0; attempt < 20; attempt++) {
      try {
        await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 15_000 });
        await page.getByLabel('Benutzername').fill(USER);
        await page.getByLabel('Passwort').fill(PASS);
        await page.getByRole('button', { name: 'Anmelden' }).click();
        await page.waitForURL(/\/arbeitsplatz$/, { timeout: 20_000 });
        return;
      } catch {
        await page.waitForTimeout(1_000);
      }
    }
    throw new Error(`global-setup: ${baseURL} never became ready for login`);
  } finally {
    await browser.close();
  }
}
