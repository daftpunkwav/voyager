/**
 * @file notesView
 * @description Notes UI preference pipeline: local cache plus backend get/set_notes_view, with user actions and agent calls treated equally.
 *
 * Responsibilities:
 * - Commit every user preference change to the local cache and the
 *   backend notes view snapshot
 * - Apply snapshots from agents (or the backend) into the UI store and
 *   route open/index/assist actions
 * - Run the explain-quote flow: compose the message and send the user
 *   turn to the floating chat
 */

import { writeKey } from '@/brand';
import { i18n } from '@/i18n';
import { chatSystemNote, openFloatingChat, sendUserTurn } from '@/bridge/chatSend';
import { getNotesView, setNotesView as setNotesViewApi } from '@/api/notes';
import { personaDisplayName } from '@/constants/personas';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from './notesUiStore';
import {
  NOTES_DENSITY_KEY,
  NOTES_FILTER_KEY,
  NOTES_FONT_KEY,
  NOTES_FONT_MAX,
  NOTES_FONT_MIN,
  NOTES_LAYOUT_KEY,
  NOTES_LIST_KEY,
  NOTES_MODE_KEY,
  NOTES_PANEL_KEY,
  NOTES_QUERY_KEY,
  NOTES_SORT_KEY,
  NOTES_SOURCE_KEY,
  NOTES_SYNC_KEY,
  NOTES_TOC_WIDTH_KEY,
  parseNotesDensity,
  parseNotesFilter,
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseNotesPanel,
  parseNotesQuery,
  parseNotesSort,
  parseNotesSourceId,
  parseNotesTocWidth,
  parseSyncScroll,
  type NotesDensity,
  type NotesFilter,
  type NotesLayout,
  type NotesListState,
  type NotesMode,
  type NotesPanel,
  type NotesSort,
} from './notePrefs';
import { buildNoteExplainMessage, parseNotesQuote, rememberNotesQuote } from './noteQuote';

export interface NotesViewSnapshot {
  font_size: number;
  mode: NotesMode;
  layout: NotesLayout;
  sync_scroll: boolean;
  list_state: NotesListState;
  sort: NotesSort;
  filter: NotesFilter;
  query: string;
  source_id: string;
  panel: NotesPanel;
  density: NotesDensity;
  persisted?: boolean;
  toc_width?: number;
  action?: 'open' | 'index' | null;
  note_id?: string | null;
  assist?: boolean;
  quote?: string;
}

export interface NotesViewPatch {
  font_size?: number;
  font_delta?: number;
  mode?: NotesMode;
  layout?: NotesLayout;
  sync_scroll?: boolean;
  list_state?: NotesListState;
  sort?: NotesSort;
  filter?: NotesFilter;
  query?: string;
  source_id?: string;
  panel?: NotesPanel;
  density?: NotesDensity;
  toc_width?: number;
  assist?: boolean;
  quote?: string;
  note_id?: string;
  index?: boolean;
}

type UiPatch = {
  fontSize?: number;
  mode?: NotesMode;
  layout?: NotesLayout;
  listState?: NotesListState;
  sort?: NotesSort;
  filter?: NotesFilter;
  query?: string;
  sourceId?: string;
  panel?: NotesPanel;
  density?: NotesDensity;
  syncScroll?: boolean;
  tocWidth?: number;
};

function cacheLocal(s: {
  fontSize: number;
  mode: NotesMode;
  layout: NotesLayout;
  listState: NotesListState;
  sort: NotesSort;
  filter: NotesFilter;
  query: string;
  sourceId: string;
  panel: NotesPanel;
  density: NotesDensity;
  syncScroll: boolean;
  tocWidth: number;
}): void {
  writeKey(NOTES_FONT_KEY, String(s.fontSize));
  writeKey(NOTES_MODE_KEY, s.mode);
  writeKey(NOTES_LAYOUT_KEY, s.layout);
  writeKey(NOTES_LIST_KEY, s.listState);
  writeKey(NOTES_SORT_KEY, s.sort);
  writeKey(NOTES_FILTER_KEY, s.filter);
  writeKey(NOTES_QUERY_KEY, s.query);
  writeKey(NOTES_SOURCE_KEY, s.sourceId);
  writeKey(NOTES_PANEL_KEY, s.panel);
  writeKey(NOTES_DENSITY_KEY, s.density);
  writeKey(NOTES_SYNC_KEY, s.syncScroll ? '1' : '0');
  writeKey(NOTES_TOC_WIDTH_KEY, String(s.tocWidth));
}

function boolish(value: unknown): boolean {
  return value === true || value === 'true' || value === 1;
}

/** Writes a backend snapshot into the store and the localStorage cache (still readable next time when the backend is unavailable). */
export function applyNotesViewSnapshot(
  raw: Partial<NotesViewSnapshot> | Record<string, unknown>
): void {
  const patch: UiPatch = {};
  if (raw.font_size != null) patch.fontSize = parseNotesFontSize(String(raw.font_size));
  if (raw.mode != null) patch.mode = parseNotesMode(String(raw.mode));
  if (raw.layout != null) patch.layout = parseNotesLayout(String(raw.layout));
  if (raw.list_state != null) patch.listState = parseNotesListState(String(raw.list_state));
  if (raw.sort != null) patch.sort = parseNotesSort(String(raw.sort));
  if (raw.filter != null) patch.filter = parseNotesFilter(String(raw.filter));
  if (raw.query != null) patch.query = parseNotesQuery(String(raw.query));
  if (raw.source_id != null) patch.sourceId = parseNotesSourceId(String(raw.source_id));
  if (raw.panel != null) patch.panel = parseNotesPanel(String(raw.panel));
  if (raw.density != null) patch.density = parseNotesDensity(String(raw.density));
  if (raw.sync_scroll != null) {
    patch.syncScroll =
      typeof raw.sync_scroll === 'boolean'
        ? raw.sync_scroll
        : parseSyncScroll(String(raw.sync_scroll));
  }
  if (raw.toc_width != null) patch.tocWidth = parseNotesTocWidth(String(raw.toc_width));
  if (Object.keys(patch).length === 0) return;
  useNotesUiStore.getState().apply(patch);
  cacheLocal(useNotesUiStore.getState());
}

export function applyNotesSettingKey(key: string, value: unknown): void {
  if (key === 'notes.ui.font_size') {
    applyNotesViewSnapshot({ font_size: Number(value) });
    return;
  }
  if (key === 'notes.ui.mode') {
    applyNotesViewSnapshot({ mode: String(value) as NotesMode });
    return;
  }
  if (key === 'notes.ui.layout') {
    applyNotesViewSnapshot({ layout: String(value) as NotesLayout });
    return;
  }
  if (key === 'notes.ui.list_state') {
    applyNotesViewSnapshot({ list_state: String(value) as NotesListState });
    return;
  }
  if (key === 'notes.ui.sort') {
    applyNotesViewSnapshot({ sort: String(value) as NotesSort });
    return;
  }
  if (key === 'notes.ui.filter') {
    applyNotesViewSnapshot({ filter: String(value) as NotesFilter });
    return;
  }
  if (key === 'notes.ui.query') {
    applyNotesViewSnapshot({ query: String(value ?? '') });
    return;
  }
  if (key === 'notes.ui.source_id') {
    applyNotesViewSnapshot({ source_id: String(value ?? '') });
    return;
  }
  if (key === 'notes.ui.panel') {
    applyNotesViewSnapshot({ panel: String(value) as NotesPanel });
    return;
  }
  if (key === 'notes.ui.density') {
    applyNotesViewSnapshot({ density: String(value) as NotesDensity });
    return;
  }
  if (key === 'notes.ui.sync_scroll') {
    applyNotesViewSnapshot({ sync_scroll: boolish(value) });
    return;
  }
  if (key === 'notes.ui.toc_width') {
    applyNotesViewSnapshot({ toc_width: Number(value) });
  }
}

export async function fetchNotesView(): Promise<NotesViewSnapshot> {
  return getNotesView<NotesViewSnapshot>();
}

export async function setNotesView(args: NotesViewPatch): Promise<NotesViewSnapshot> {
  return setNotesViewApi<NotesViewSnapshot>({ ...args } as Record<string, unknown>);
}

/** Writes back only the fields changed this time. Optimistic updates already land in the store; events / settings.changed re-align later. */
export function persistNotesView(args: NotesViewPatch): void {
  void setNotesView(args).catch(() => {
    /* Backend unreachable: the UI trusts the local cache instead of pretending it synced */
  });
}

export function commitNotesFont(size: number): void {
  const fontSize = parseNotesFontSize(String(size));
  useNotesUiStore.getState().apply({ fontSize });
  writeKey(NOTES_FONT_KEY, String(fontSize));
  persistNotesView({ font_size: fontSize });
}

export function commitNotesMode(mode: NotesMode): void {
  useNotesUiStore.getState().apply({ mode });
  writeKey(NOTES_MODE_KEY, mode);
  persistNotesView({ mode });
}

export function commitNotesLayout(layout: NotesLayout): void {
  useNotesUiStore.getState().apply({ layout });
  writeKey(NOTES_LAYOUT_KEY, layout);
  persistNotesView({ layout });
}

export function commitNotesListState(listState: NotesListState): void {
  useNotesUiStore.getState().apply({ listState });
  writeKey(NOTES_LIST_KEY, listState);
  persistNotesView({ list_state: listState });
}

export function commitNotesSort(sort: NotesSort): void {
  useNotesUiStore.getState().apply({ sort });
  writeKey(NOTES_SORT_KEY, sort);
  persistNotesView({ sort });
}

export function commitNotesFilter(filter: NotesFilter): void {
  useNotesUiStore.getState().apply({ filter });
  writeKey(NOTES_FILTER_KEY, filter);
  persistNotesView({ filter });
}

let queryTimer: ReturnType<typeof setTimeout> | undefined;

export function commitNotesQuery(query: string): void {
  const q = parseNotesQuery(query);
  useNotesUiStore.getState().apply({ query: q });
  writeKey(NOTES_QUERY_KEY, q);
  if (queryTimer) clearTimeout(queryTimer);
  queryTimer = setTimeout(() => persistNotesView({ query: q }), 400);
}

export function commitNotesSourceId(sourceId: string): void {
  const id = parseNotesSourceId(sourceId);
  useNotesUiStore.getState().apply({ sourceId: id });
  writeKey(NOTES_SOURCE_KEY, id);
  persistNotesView({ source_id: id });
}

export function commitNotesPanel(panel: NotesPanel): void {
  useNotesUiStore.getState().apply({ panel });
  writeKey(NOTES_PANEL_KEY, panel);
  persistNotesView({ panel });
}

export function commitNotesDensity(density: NotesDensity): void {
  useNotesUiStore.getState().apply({ density });
  writeKey(NOTES_DENSITY_KEY, density);
  persistNotesView({ density });
}

export function commitNotesSyncScroll(syncScroll: boolean): void {
  useNotesUiStore.getState().apply({ syncScroll });
  writeKey(NOTES_SYNC_KEY, syncScroll ? '1' : '0');
  persistNotesView({ sync_scroll: syncScroll });
}

export function commitNotesTocWidth(width: number, persist = true): void {
  const tocWidth = parseNotesTocWidth(String(width));
  useNotesUiStore.getState().apply({ tocWidth });
  writeKey(NOTES_TOC_WIDTH_KEY, String(tocWidth));
  if (persist) persistNotesView({ toc_width: tocWidth });
}

export function bumpNotesFont(delta: number): void {
  const cur = useNotesUiStore.getState().fontSize;
  const next = Math.min(NOTES_FONT_MAX, Math.max(NOTES_FONT_MIN, cur + delta));
  commitNotesFont(next);
}

export function openNotesAssist(): void {
  persistNotesView({ assist: true });
}

/** Opens the floating chat and hands the selection to the recon persona. The quote is never persisted; user drag-selections and agent set_notes_view share this path.
 *  Sending goes through sendUserTurn (same quota guards as the rest of the app); the floating window / system bubbles follow the bridge contract. */
export function explainNotesQuote(quote: string): void {
  const q = parseNotesQuote(quote);
  if (!q) return;
  rememberNotesQuote(q);
  const title = useNoteStore.getState().editorTitle;
  const content = buildNoteExplainMessage({
    quote: q,
    title,
    agentName: personaDisplayName('recon'),
  });
  openFloatingChat();
  void sendUserTurn(content).catch((err: unknown) => {
    chatSystemNote(err instanceof Error ? err.message : i18n.t('notes:sendFailed'));
  });
}
