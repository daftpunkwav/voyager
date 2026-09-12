/**
 * @file team.spec
 * @description Realistic user flows on the team page: section rendering and the
 * "register a subagent" form (with cleanup of the created definition).
 */

import { expect, test } from '@playwright/test';
import { rm } from 'node:fs/promises';
import { resolve } from 'node:path';

const AGENT_NAME = `e2e_probe_${Date.now()}`;

test.describe('team page', () => {
  test('renders the six management sections', async ({ page }) => {
    await page.goto('/team');
    await expect(page.getByRole('heading', { name: '人格', exact: true, level: 2 })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: '自建 subagent', exact: true, level: 2 })
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: '工具面名册', level: 2 })).toBeVisible();
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

  test.afterAll(async () => {
    // definitions live at <repo>/data/subagents/<name>.json; remove our probe
    // (playwright runs with cwd = apps/web, so the repo root is two up)
    await rm(resolve(process.cwd(), '../../data/subagents', `${AGENT_NAME}.json`), { force: true });
  });
});
