/**
 * @file noteListing
 * @description Note listing pipeline: snippets, linked-source resolution, filtering, sorting, and day-based grouping.
 *
 * Responsibilities:
 * - Normalize list rows: snippets stripped of markup, source-id
 *   compatibility (project_id vs source_id), and timestamp unification
 * - Apply filter/sort/day-grouping for the notes home and the card
 *   recency groups
 * - Detect placeholder titles to single out agent-created unnamed notes
 */

import { formatRelativeTime } from '@/utils/date';
import { i18n } from '@/i18n';
import type { NotesFilter, NotesSort } from './notePrefs';

const PLACEHOLDER_TITLE = /^(新笔记|无标题|untitled|草稿)(\s|$)/i;

type NoteListItem = {
  title?: string;
  pinned?: boolean;
  updated_ts?: number;
  updated_at?: string;
  created_ts?: number;
  created_at?: string | number;
  project_id?: string;
  source_id?: string;
  excerpt?: string;
  content?: string;
};

/** Placeholder titles; used to single out unnamed notes when an agent creates several in a row. */
export function isPlaceholderTitle(title: string | undefined): boolean {
  const t = (title || '').trim();
  if (!t) return true;
  return PLACEHOLDER_TITLE.test(t);
}

export function startOfLocalDayMs(now = Date.now()): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Backend list/get payloads use source_id; the legacy frontend field was project_id. */
export function noteSourceId(n: { project_id?: string; source_id?: string }): string {
  return n.project_id || n.source_id || '';
}

/** list_notes returns only excerpt, never content; content is only available from the full-text endpoint. */
export function noteSnippet(n: { excerpt?: string; content?: string }): string {
  return (n.excerpt || n.content || '').replace(/[#*`]/g, '').replace(/\s+/g, ' ').trim();
}

function epochToMs(ts?: number, fallback?: string | number): number {
  if (typeof ts === 'number' && ts > 0) {
    return ts < 1e12 ? ts * 1000 : ts;
  }
  if (typeof fallback === 'number' && fallback > 0) {
    return fallback < 1e12 ? fallback * 1000 : fallback;
  }
  if (typeof fallback === 'string' && fallback) {
    return Date.parse(fallback) || 0;
  }
  return 0;
}

type NoteTimestamps = {
  updated_at?: string;
  updated_ts?: number;
  created_at?: string | number;
  created_ts?: number;
};

/** Normalizes to milliseconds; backend updated_ts is usually epoch seconds while updated_at is ISO. */
export function noteUpdatedMs(n: NoteTimestamps): number {
  return epochToMs(n.updated_ts, n.updated_at);
}

export function noteCreatedMs(n: NoteTimestamps): number {
  const ms = epochToMs(n.created_ts, n.created_at);
  return ms > 0 ? ms : noteUpdatedMs(n);
}

export function noteUpdatedLabel(n: NoteTimestamps): string {
  if (n.updated_at) return formatRelativeTime(n.updated_at);
  const ms = noteUpdatedMs(n);
  if (ms > 0) return formatRelativeTime(new Date(ms).toISOString());
  return '';
}

export interface NotesListingOpts<T = NoteListItem> {
  query?: string;
  filter?: NotesFilter;
  sort?: NotesSort;
  sourceId?: string;
  extraText?: (n: T) => string;
}

/** Pinned notes always come first; the rest sort by recently updated / recently created / title. */
export function sortNotes<T extends NoteListItem>(notes: T[], sort: NotesSort): T[] {
  return [...notes].sort((a, b) => {
    const pin = Number(Boolean(b.pinned)) - Number(Boolean(a.pinned));
    if (pin !== 0) return pin;
    if (sort === 'title') {
      // Sort locale follows the UI language (zh-CN keeps pinyin ordering)
      return (a.title || '').localeCompare(b.title || '', i18n.resolvedLanguage ?? 'zh-CN');
    }
    if (sort === 'created') {
      return noteCreatedMs(b) - noteCreatedMs(a);
    }
    return noteUpdatedMs(b) - noteUpdatedMs(a);
  });
}

export function filterNotes<T extends NoteListItem>(
  notes: T[],
  filter: NotesFilter,
  now = Date.now()
): T[] {
  if (filter === 'all') return notes;
  if (filter === 'pinned') return notes.filter((n) => Boolean(n.pinned));
  if (filter === 'untitled') return notes.filter((n) => isPlaceholderTitle(n.title));
  if (filter === 'unlinked') return notes.filter((n) => !noteSourceId(n));
  const start = startOfLocalDayMs(now);
  return notes.filter((n) => noteCreatedMs(n) >= start);
}

/** Homepage listing pipeline: linked source, then keyword, then filter, then sort. Pure function, shared by the page and the agent snapshot. */
export function applyNotesListing<T extends NoteListItem>(
  notes: T[],
  opts: NotesListingOpts<T>,
  now = Date.now()
): T[] {
  const sourceId = opts.sourceId || '';
  const q = (opts.query || '').trim().toLowerCase();
  let out = notes;
  if (sourceId) out = out.filter((n) => noteSourceId(n) === sourceId);
  if (q) {
    out = out.filter((n) => {
      const title = (n.title || '').toLowerCase();
      const snippet = noteSnippet(n).toLowerCase();
      const extra = (opts.extraText?.(n) ?? '').toLowerCase();
      return title.includes(q) || snippet.includes(q) || extra.includes(q);
    });
  }
  out = filterNotes(out, opts.filter ?? 'all', now);
  return sortNotes(out, opts.sort ?? 'updated');
}

export interface NotesBucket<T> {
  id: string;
  label: string;
  items: T[];
}

/** Groups the list by day so bursts of agent-created notes stay scannable; title sorting skips grouping. */
export function groupNotesByRecency<T extends NoteListItem>(
  notes: T[],
  by: 'updated' | 'created',
  now = Date.now()
): NotesBucket<T>[] {
  const start = startOfLocalDayMs(now);
  const yesterday = start - 86_400_000;
  const week = start - 6 * 86_400_000;
  const buckets: Record<string, T[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  };
  for (const n of notes) {
    const ms = by === 'created' ? noteCreatedMs(n) : noteUpdatedMs(n);
    if (ms >= start) buckets.today.push(n);
    else if (ms >= yesterday) buckets.yesterday.push(n);
    else if (ms >= week) buckets.week.push(n);
    else buckets.older.push(n);
  }
  const labels: Record<string, string> = {
    today: i18n.t('notes:bucket.today'),
    yesterday: i18n.t('notes:bucket.yesterday'),
    week: i18n.t('notes:bucket.week'),
    older: i18n.t('notes:bucket.older'),
  };
  return (['today', 'yesterday', 'week', 'older'] as const)
    .filter((id) => buckets[id].length > 0)
    .map((id) => ({ id, label: labels[id], items: buckets[id] }));
}
