import { defineConfig } from '@playwright/test';

// The kiosk smoke launches the built Electron app (`_electron`). No browser
// projects — Electron brings its own Chromium.
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
});
