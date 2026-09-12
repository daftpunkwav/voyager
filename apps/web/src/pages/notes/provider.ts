/**
 * @file provider
 * @description Page probe for the notes page: reports list count, view state, current note title, and the explain-selection pointer — never note content.
 *
 * Responsibilities:
 * - Hold the module-level list count cache written by NotesPage (react-
 *   query data is unreadable here)
 * - Compose the index or workspace summary line from the stores: view
 *   state, font size, title, quote pointer, and trash panel
 * - Skip the count while the list never arrived; a real 0 is reported
 *   as-is
 */

import type { PageProbe } from '@/bridge/pageContext';
import { i18n } from '@/i18n';
import { lastNotesExplainQuote } from './noteQuote';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from './notesUiStore';

/** Module cache for the list count (same pattern as noteQuote.ts): the list
 * data lives in react-query, which the provider cannot read. NotesPage writes
 * it when data arrives; null = the list never arrived (do not report a fake 0). */
let listCount: number | null = null;

export function rememberNotesListCount(count: number | null): void {
  listCount = count;
}

export function lastNotesListCount(): number | null {
  return listCount;
}

/** Title clipping so the single-line summary stays bounded. */
function clipTitle(title: string, max = 40): string {
  return title.trim().slice(0, max);
}

export const notesProvider: PageProbe = {
  page: 'notes',
  report() {
    const { editingNoteId, editorTitle } = useNoteStore.getState();
    const { mode, layout, fontSize, listState, sort, filter, query, panel } =
      useNotesUiStore.getState();
    const title = clipTitle(editorTitle || '');
    const quoted = lastNotesExplainQuote().trim().slice(0, 20);
    // List count: omit it while the cache is null (the list never arrived); a real 0 is reported as-is
    const n = listCount;
    const countPart = n === null ? '' : i18n.t('notes:probe.count', { n });
    const counts = n === null ? undefined : { notes: n };
    if (editingNoteId && editingNoteId !== 'new') {
      return {
        summary: `${i18n.t('notes:probe.workspace')}${countPart} · ${mode} · ${i18n.t('notes:probe.fontSize', { size: fontSize })}${title ? ` · ${i18n.t('notes:probe.title', { title })}` : ''}${quoted ? ` · ${i18n.t('notes:probe.quote', { quote: quoted })}` : ''}${panel === 'trash' ? ` · ${i18n.t('notes:probe.trash')}` : ''}`,
        selected: editingNoteId,
        counts,
      };
    }
    const q = query.trim().slice(0, 20);
    return {
      summary: `${i18n.t('notes:probe.index')}${countPart} · ${layout} · ${listState === 'archived' ? i18n.t('notes:state.archived') : i18n.t('notes:state.active')} · ${sort} · ${filter}${q ? ` · ${i18n.t('notes:probe.query', { query: q })}` : ''}${panel === 'trash' ? ` · ${i18n.t('notes:probe.trash')}` : ''}`,
      selected: editingNoteId === 'new' ? 'new' : '',
      counts,
    };
  },
};
