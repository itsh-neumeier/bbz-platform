import { expect, test } from '@playwright/test';

// Foundation smoke. Full mandatory E2E scripts (MASTER_PROMPT §24/§35/§36.1)
// are added with the features they exercise.
test('app shell loads and shows the workplace page', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/BBZ/);
  await expect(page.getByRole('heading', { name: 'Arbeitsplatz' })).toBeVisible();
});
