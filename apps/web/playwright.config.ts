import { defineConfig } from '@playwright/test';

// E2E smoke only in the foundation phase. The mandatory end-to-end scripts from
// MASTER_PROMPT §24/§35/§36.1 are added with the features they cover.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: { baseURL: 'http://localhost:5173' },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
});
