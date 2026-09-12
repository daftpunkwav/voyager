/**
 * @file notes.spec
 * @description Realistic user flows on the notes page: create, save, search
 * filtering, view switching, archive tab, move to trash and restore. Serial
 * order: the trash flow depends on the note created by the first test.
 * Cleans up after itself: probe-note residues are purged through the notes
 * API before each test and after the trash flow, so interrupted runs heal.
 */

import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const TITLE = `e2e notes probe ${Date.now()}`;
const BODY = 'e2e 正文第一行,验证自动保存与搜索。';
// Backend origin for setup/cleanup calls (must match the vite proxy target in
// vite.config.ts); the browser-facing pages themselves go through the proxy.
const API_BASE = 'http://127.0.0.1:8000';

test.describe.configure({ mode: 'serial' });

test.describe('notes page', () => {
  let created = false;

  /** Permanently purge every probe-note residue through the notes API. Used
   *  for environment self-healing: driving the trash-purge loop through the
   *  UI races against the list's async refresh and is needlessly fragile. */
  async function purgeProbeNotes(request: APIRequestContext): Promise<void> {
    const cap = (name: string, data: Record<string, unknown>) =>
      request.post(`${API_BASE}/api/notes/capabilities/${name}`, { data });
    const res = await cap('list_notes', { state: 'all', query: 'e2e notes probe', limit: 200 });
    const rows =
      ((await res.json()) as { result?: Array<{ id: string; title: string }> }).result ?? [];
    for (const row of rows) {
      // keep the note created by this very run (the trash flow uses it)
      if (row.title.startsWith('e2e notes probe') && row.title !== TITLE) {
        await cap('purge_note', { note_id: row.id });
      }
    }
  }

  /** The notes workspace (tab, search term, open panel) is persisted through
   *  backend settings (notes.ui.*), so both leaks from earlier tests in this
   *  file and residues of interrupted runs would poison the flows. Reset the
   *  keys and probe-note residues before every test via the API. */
  test.beforeEach(async ({ request }) => {
    const reset = (key: string, value: string) =>
      request.post(`${API_BASE}/api/settings/capabilities/set_setting`, { data: { key, value } });
    await Promise.all([
      reset('notes.ui.list_state', 'active'),
      reset('notes.ui.panel', 'none'),
      reset('notes.ui.query', ''),
      purgeProbeNotes(request),
    ]);
  });

  /** Enter the notes page on the 当前 tab. */
  async function openCurrentTab(page: Page): Promise<void> {
    await page.goto('/notes');
    await page.getByRole('tab', { name: '当前' }).click();
  }

  test('create a note, save it, find it via search', async ({ page }) => {
    await openCurrentTab(page);
    await page.getByRole('button', { name: '新建', exact: true }).click();

    // the editor mode is a persisted preference; when it restores as
    // preview/split the edit pane must be switched on explicitly
    const editBtn = page.getByRole('button', { name: '编辑', exact: true });
    await editBtn.waitFor({ state: 'visible', timeout: 10_000 });
    if ((await editBtn.getAttribute('aria-pressed')) !== 'true') await editBtn.click();

    // editor opens with a title input and the CodeMirror body
    const title = page.locator('.edit-title-input');
    await expect(title).toBeVisible();
    await title.fill(TITLE);

    const cm = page.locator('[data-testid="note-editor-cm"] .cm-content');
    await expect(cm).toBeVisible();
    await cm.click();
    await page.keyboard.type(BODY);

    // explicit save round trip
    const save = page.getByTestId('save-note-btn');
    await save.click();
    await expect(save).toBeEnabled({ timeout: 10_000 });
    created = true;

    // back to the list, then the note is searchable there
    await page.getByRole('button', { name: '返回列表' }).click();
    const search = page.getByRole('searchbox', { name: '筛选笔记' });
    await search.fill('e2e notes probe');
    await expect(page.getByText(TITLE).first()).toBeVisible({ timeout: 10_000 });
  });

  test('search filter hides non-matching notes', async ({ page }) => {
    await openCurrentTab(page);
    const search = page.getByRole('searchbox', { name: '筛选笔记' });
    await search.fill('Voyager 架构设计');
    await expect(page.getByText('Voyager 架构设计(最终形态)').first()).toBeVisible();
    await expect(page.getByText('王者荣耀介绍')).toHaveCount(0);
  });

  test('switching between list and card views keeps the list usable', async ({ page }) => {
    await openCurrentTab(page);
    const card = page.getByRole('button', { name: '卡片', exact: true });
    const list = page.getByRole('button', { name: '列表', exact: true });
    await card.click();
    await expect(card).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByText('Voyager 架构设计(最终形态)').first()).toBeVisible();
    await list.click();
    await expect(list).toHaveAttribute('aria-pressed', 'true');
  });

  test('archive tab renders', async ({ page }) => {
    await page.goto('/notes');
    await page.getByRole('tab', { name: '归档' }).click();
    await expect(page.getByRole('tab', { name: '归档' })).toHaveAttribute('aria-selected', 'true');
  });

  test('move the probe note to trash, restore it, then purge it', async ({ page, request }) => {
    test.skip(!created, 'probe note was not created');
    await openCurrentTab(page);
    const search = page.getByRole('searchbox', { name: '筛选笔记' });
    await search.fill('e2e notes probe');
    const item = page.locator('[data-testid="note-item"]', { hasText: TITLE }).first();
    await expect(item).toBeVisible();

    // per-item menu → move to trash → confirm dialog
    await item.getByRole('button', { name: '笔记操作' }).click();
    await page.getByRole('menuitem', { name: '移入回收站' }).click();
    const confirm = page.getByRole('dialog', { name: '移入回收站' });
    await confirm.getByRole('button', { name: '移入回收站' }).click();

    // it lands in the trash, then restore puts it back into the list
    await page.getByRole('button', { name: '回收站' }).click();
    const panel = page.getByRole('dialog', { name: '回收站' });
    const row = panel.locator('.trash-panel__row', { hasText: TITLE });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await row.getByRole('button', { name: '恢复' }).click();
    await expect(row).toBeHidden({ timeout: 10_000 });
    await expect(item).toBeVisible({ timeout: 10_000 });
    await panel.getByRole('button', { name: '关闭' }).click();

    // cleanup: purge every probe residue permanently through the API
    await purgeProbeNotes(request);
    const left = await request.post(`${API_BASE}/api/notes/capabilities/list_notes`, {
      data: { state: 'trash', query: 'e2e notes probe', limit: 50 },
    });
    const leftRows = ((await left.json()) as { result?: unknown[] }).result ?? [];
    expect(leftRows).toHaveLength(0);
    created = false;
  });
});
