/**
 * @file notesView
 * @description Unit tests for applying the backend notes UI snapshot:
 * writing view/filter/sort/TOC width into the store and single-key
 * settings.changed updates.
 */

import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { initI18n } from '@/i18n';
import { applyNotesSettingKey, applyNotesViewSnapshot } from '@/pages/notes/notesView';
import { useNotesUiStore } from '@/pages/notes/notesUiStore';

// notesView imports i18n-resolving modules (noteQuote etc.); init once for the file
beforeAll(() => {
  initI18n();
});

afterEach(() => {
  useNotesUiStore.getState().apply({
    fontSize: 15,
    mode: 'edit',
    layout: 'list',
    listState: 'active',
    sort: 'updated',
    filter: 'all',
    query: '',
    sourceId: '',
    panel: 'none',
    density: 'comfortable',
    syncScroll: true,
    tocWidth: 188,
  });
});

describe('applyNotesViewSnapshot', () => {
  it('writes the backend notes UI snapshot into the store', () => {
    applyNotesViewSnapshot({
      font_size: 18,
      mode: 'preview',
      layout: 'card',
      sync_scroll: false,
      list_state: 'archived',
    });
    const s = useNotesUiStore.getState();
    expect(s.fontSize).toBe(18);
    expect(s.mode).toBe('preview');
    expect(s.layout).toBe('card');
    expect(s.syncScroll).toBe(false);
    expect(s.listState).toBe('archived');
  });

  it('writes filter and sort', () => {
    applyNotesViewSnapshot({
      sort: 'created',
      filter: 'untitled',
      query: 'design',
      panel: 'trash',
      density: 'compact',
    });
    const s = useNotesUiStore.getState();
    expect(s.sort).toBe('created');
    expect(s.filter).toBe('untitled');
    expect(s.query).toBe('design');
    expect(s.panel).toBe('trash');
    expect(s.density).toBe('compact');
  });

  it('writes the TOC width', () => {
    applyNotesViewSnapshot({ toc_width: 260 });
    expect(useNotesUiStore.getState().tocWidth).toBe(260);
    applyNotesSettingKey('notes.ui.toc_width', 80);
    expect(useNotesUiStore.getState().tocWidth).toBe(148);
  });

  it('settings.changed writes a single key without touching the global font-scale key', () => {
    applyNotesSettingKey('notes.ui.font_size', 16);
    applyNotesSettingKey('appearance.font_scale', 1.2);
    expect(useNotesUiStore.getState().fontSize).toBe(16);
  });
});
