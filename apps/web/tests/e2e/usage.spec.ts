/**
 * @file usage.spec
 * @description Realistic user flows on the usage dashboard: dashboard sections,
 * range switching (network round trip), model/provider breakdown toggle, refresh.
 */

import { expect, test } from '@playwright/test';

test.describe('usage page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/usage');
    await expect(page.getByRole('heading', { name: '今日 token 配额' })).toBeVisible();
  });

  test('renders quota, heatmap and model breakdown', async ({ page }) => {
    await expect(page.getByText(/已用 0·上限 不限|已用/)).toBeVisible();
    await expect(page.getByRole('img', { name: '按日调用热力图' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '模型用量' })).toBeVisible();
    // breakdown rows render with model names
    await expect(page.getByText('MiniMax-M3').first()).toBeVisible();
  });

  test('switching the time range refetches usage history', async ({ page }) => {
    // the dashboard defaults to 30 days; switching to 7 must trigger a refetch
    const history = page.waitForRequest(
      (req) =>
        req.url().includes('/api/llm/capabilities/get_usage_stats') && req.method() === 'POST',
      { timeout: 5_000 }
    );
    await page.getByRole('button', { name: '最近 7 天' }).click();
    await expect(history).resolves.toBeDefined();
    await expect(page.getByRole('button', { name: '最近 7 天' })).toHaveClass(/active/);
  });

  test('toggling the breakdown dimension switches the list', async ({ page }) => {
    const provider = page.getByRole('button', { name: '供应商', exact: true });
    const model = page.getByRole('button', { name: '模型', exact: true });
    await provider.click();
    await expect(provider).toHaveClass(/active/);
    await model.click();
    await expect(model).toHaveClass(/active/);
  });

  test('refresh button keeps the dashboard interactive', async ({ page }) => {
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    await expect(page.getByRole('img', { name: '按日调用热力图' })).toBeVisible({
      timeout: 10_000,
    });
  });
});
