import { defineConfig, devices } from '@playwright/test';

// The mandatory end-to-end scripts from MASTER_PROMPT §24/§35/§36.1. The specs
// share one seeded backend (server/scripts/seed_e2e.py) and some walk an event
// through its whole lifecycle, so they run serially — correctness over speed.
//
// `E2E_BASE_URL` points the run at an already-running SPA (skips the dev server);
// unset, Playwright starts `npm run dev` itself.
const externalBaseURL = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: './e2e',
  globalSetup: './playwright.global-setup.ts',
  timeout: 30_000,
  // a cold API (first login pays the Argon2 cost) can miss the 5 s default
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [['github'], ['list'], ['html', { open: 'never' }]]
    : 'list',
  use: {
    baseURL: externalBaseURL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: externalBaseURL
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
      },
});
