/**
 * @file team.spec
 * @description Realistic user flows on the team page: section rendering and the
 * "register a subagent" form (with cleanup of the created definition).
 */

import { expect, test, type APIRequestContext } from '@playwright/test';

const AGENT_NAME = `e2e_probe_${Date.now()}`;
// Backend origin for setup/cleanup calls (must match the vite proxy target in
// vite.config.ts); the browser-facing pages themselves go through the proxy.
const API_BASE = 'http://127.0.0.1:8000';

test.describe('team page', () => {
  test('renders the management sections', async ({ page }) => {
    await page.goto('/team');
    // the tool roster section renders a toolbar without a section heading,
    // so the page exposes five level-2 headings
    for (const section of ['人格', '自建子代理', '注册子代理', '可恢复任务', '子代理实例']) {
      await expect(page.getByRole('heading', { name: section, level: 2 })).toBeVisible();
    }
    // persona cards: at least the five built-in personas
    for (const persona of ['Lucien', 'Iris', 'Elio', 'Miyai', 'Atlas']) {
      await expect(page.getByRole('heading', { name: persona, level: 3 })).toBeVisible();
    }
  });

  test('registering a subagent definition adds it to the grid', async ({ page }) => {
    await page.goto('/team');
    const name = page.getByRole('textbox', { name: '名称' });
    await name.scrollIntoViewIfNeeded();
    await name.fill(AGENT_NAME);
    await page.getByRole('textbox', { name: '描述' }).fill('e2e probe agent, safe to delete');

    await page.getByRole('button', { name: '注册', exact: true }).click();

    // success feedback + the new definition shows up in the grid
    await expect(page.getByRole('heading', { name: AGENT_NAME, level: 3 })).toBeVisible({
      timeout: 10_000,
    });
  });

  test.afterAll(async ({ request }: { request: APIRequestContext }) => {
    // purge the probe definition through the API: the on-disk location of
    // subagent definitions follows the backend's data root, which differs
    // between a developer machine and a fresh CI environment
    await request.post(`${API_BASE}/api/agent/capabilities/subagent`, {
      data: { action: 'unregister', name: AGENT_NAME },
    });
  });
});
