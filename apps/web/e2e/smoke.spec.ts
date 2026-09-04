import { expect, test } from '@playwright/test';

// Foundation smoke — the shell boots and an unauthenticated visitor lands on a
// working login screen. Needs no backend. The mandatory E2E scripts
// (MASTER_PROMPT §24/§35/§36.1) live in their own specs.
test('the shell boots and routes an unauthenticated visitor to the login screen', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
  await expect(page).toHaveTitle(/BBZ/);
  await expect(page.getByLabel('Benutzername')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Anmelden' })).toBeVisible();
});
