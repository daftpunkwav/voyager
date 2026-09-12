/**
 * @file notePrefs
 * @description Notes-page UI preferences: localStorage keys, allowed ranges, and parsers. List filtering is handled elsewhere.
 *
 * Responsibilities:
 * - Define the localStorage keys, option lists (flat i18n label keys), and
 *   allowed ranges for every notes preference
 * - Parse and clamp raw stored values into valid preference values with
 *   defined defaults
 */

export const NOTES_MODE_KEY = 'notes-mode';
export const NOTES_LAYOUT_KEY = 'notes-layout';
export const NOTES_SPLIT_KEY = 'notes-split';
export const NOTES_FONT_KEY = 'notes-font';
export const NOTES_SYNC_KEY = 'notes-sync-scroll';
export const NOTES_LIST_KEY = 'notes-list-state';
export const NOTES_SORT_KEY = 'notes-sort';
export const NOTES_FILTER_KEY = 'notes-filter';
export const NOTES_QUERY_KEY = 'notes-query';
export const NOTES_SOURCE_KEY = 'notes-source';
export const NOTES_PANEL_KEY = 'notes-panel';
export const NOTES_DENSITY_KEY = 'notes-density';
export const NOTES_TOC_WIDTH_KEY = 'notes-toc-width';

export const NOTES_FONT_MIN = 12;
export const NOTES_FONT_MAX = 24;
export const NOTES_FONT_DEFAULT = 15;
export const NOTES_TOC_WIDTH_MIN = 148;
export const NOTES_TOC_WIDTH_MAX = 480;
export const NOTES_TOC_WIDTH_DEFAULT = 188;

export type NotesMode = 'edit' | 'preview' | 'split';
export type NotesLayout = 'list' | 'card';
export type NotesListState = 'active' | 'archived';
export type NotesSort = 'updated' | 'created' | 'title';
export type NotesFilter = 'all' | 'pinned' | 'untitled' | 'unlinked' | 'today';
export type NotesPanel = 'none' | 'trash';
export type NotesDensity = 'comfortable' | 'compact';

/** Labels are flat i18n keys in the notes namespace; resolve with t(`notes:${label}`). */
export const NOTES_SORT_OPTIONS: { value: NotesSort; label: string }[] = [
  { value: 'updated', label: 'sort.updated' },
  { value: 'created', label: 'sort.created' },
  { value: 'title', label: 'sort.title' },
];

export const NOTES_FILTER_OPTIONS: { value: NotesFilter; label: string }[] = [
  { value: 'all', label: 'filter.all' },
  { value: 'pinned', label: 'filter.pinned' },
  { value: 'untitled', label: 'filter.untitled' },
  { value: 'unlinked', label: 'filter.unlinked' },
  { value: 'today', label: 'filter.today' },
];

const QUERY_MAX = 80;
const SOURCE_MAX = 80;

export function parseNotesMode(modeRaw: string | null | undefined): NotesMode {
  if (modeRaw === 'edit' || modeRaw === 'preview' || modeRaw === 'split') return modeRaw;
  return 'edit';
}

export function parseNotesLayout(raw: string | null | undefined): NotesLayout {
  return raw === 'card' ? 'card' : 'list';
}

export function parseNotesListState(raw: string | null | undefined): NotesListState {
  return raw === 'archived' ? 'archived' : 'active';
}

export function parseSplitRatio(raw: string | null | undefined): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0.55;
  return Math.min(0.72, Math.max(0.32, n));
}

export function parseNotesFontSize(raw: string | null | undefined): number {
  if (raw == null || raw === '') return NOTES_FONT_DEFAULT;
  const n = Number(raw);
  if (!Number.isFinite(n)) return NOTES_FONT_DEFAULT;
  return Math.min(NOTES_FONT_MAX, Math.max(NOTES_FONT_MIN, Math.round(n)));
}

export function parseNotesTocWidth(raw: string | null | undefined): number {
  if (raw == null || raw === '') return NOTES_TOC_WIDTH_DEFAULT;
  const n = Number(raw);
  if (!Number.isFinite(n)) return NOTES_TOC_WIDTH_DEFAULT;
  return Math.min(NOTES_TOC_WIDTH_MAX, Math.max(NOTES_TOC_WIDTH_MIN, Math.round(n)));
}

export function parseSyncScroll(raw: string | null | undefined): boolean {
  if (raw === '0') return false;
  return true;
}

export function parseNotesSort(raw: string | null | undefined): NotesSort {
  if (raw === 'created' || raw === 'title' || raw === 'updated') return raw;
  return 'updated';
}

export function parseNotesFilter(raw: string | null | undefined): NotesFilter {
  if (raw === 'pinned' || raw === 'untitled' || raw === 'unlinked' || raw === 'today') return raw;
  return 'all';
}

export function parseNotesPanel(raw: string | null | undefined): NotesPanel {
  return raw === 'trash' ? 'trash' : 'none';
}

export function parseNotesDensity(raw: string | null | undefined): NotesDensity {
  return raw === 'compact' ? 'compact' : 'comfortable';
}

export function parseNotesQuery(raw: string | null | undefined): string {
  return String(raw ?? '').slice(0, QUERY_MAX);
}

export function parseNotesSourceId(raw: string | null | undefined): string {
  const id = String(raw ?? '').trim();
  if (!id || id.includes('/') || id.includes('\\') || id.includes('..')) return '';
  return id.slice(0, SOURCE_MAX);
}
