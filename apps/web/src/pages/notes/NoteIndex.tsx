/**
 * @file NoteIndex
 * @description Notes home page: renders the listing only (list / card layouts) and never opens the editor.
 *
 * Archive, delete, and export are available per item and from the bulk
 * selection bar.
 *
 * Responsibilities:
 * - Render the notes home: layout switch, search, sort/filter/source
 *   selectors, and density control (all state raised to the page)
 * - Show the grouped listing (list/card) with per-item and bulk actions
 * - Slide in the bulk-selection bar with the height+opacity animation
 *   timing matched to the CSS exit duration
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GlassSelect } from '@/components/common/GlassSelect';
import type { Note } from '@/api/types';
import { applyNotesListing, groupNotesByRecency, noteSourceId } from './noteListing';
import {
  NOTES_FILTER_OPTIONS,
  NOTES_SORT_OPTIONS,
  type NotesDensity,
  type NotesFilter,
  type NotesLayout,
  type NotesListState,
  type NotesSort,
} from './notePrefs';
import { NotesAssistButton, NotesNewButton } from './NotesRailActions';
import { NoteList } from './NoteList';

interface NoteIndexProps {
  notes: Note[];
  layout: NotesLayout;
  listState: NotesListState;
  onLayoutChange: (layout: NotesLayout) => void;
  onListStateChange: (state: NotesListState) => void;
  query: string;
  onQuery: (q: string) => void;
  sort: NotesSort;
  onSort: (sort: NotesSort) => void;
  filter: NotesFilter;
  onFilter: (filter: NotesFilter) => void;
  sourceId: string;
  onSourceId: (id: string) => void;
  density: NotesDensity;
  onDensity: (density: NotesDensity) => void;
  projectOptions: { value: string; label: string }[];
  projectNames: Map<string, string>;
  onOpen: (note: Note) => void;
  onNew: () => void;
  onTrash: () => void;
  onAssist: () => void;
  onPin: (note: Note, pinned: boolean) => void;
  onArchive: (ids: string[], archived: boolean) => void;
  onExport: (ids: string[]) => void;
  onDelete: (ids: string[]) => void;
  busy?: boolean;
  empty: boolean;
}

/** Matches the notes.css --notes-bulk-ms exit animation duration. */
const BULK_BAR_MS = 420;

export function NoteIndex({
  notes,
  layout,
  listState,
  onLayoutChange,
  onListStateChange,
  query,
  onQuery,
  sort,
  onSort,
  filter,
  onFilter,
  sourceId,
  onSourceId,
  density,
  onDensity,
  projectOptions,
  projectNames,
  onOpen,
  onNew,
  onTrash,
  onAssist,
  onPin,
  onArchive,
  onExport,
  onDelete,
  busy = false,
  empty,
}: NoteIndexProps) {
  const { t } = useTranslation('notes');
  const archived = listState === 'archived';
  const compact = density === 'compact';
  const hasProjects = projectOptions.length > 0;

  const shown = useMemo(
    () =>
      applyNotesListing(notes, {
        query,
        filter,
        sort,
        sourceId,
        extraText: (n) => projectNames.get(noteSourceId(n)) ?? '',
      }),
    [notes, query, filter, sort, sourceId, projectNames]
  );

  const buckets = useMemo(() => {
    if (layout !== 'list' || sort === 'title') return null;
    return groupNotesByRecency(shown, sort === 'created' ? 'created' : 'updated');
  }, [layout, sort, shown]);

  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null);
  const [bulkMounted, setBulkMounted] = useState(false);
  const [bulkExiting, setBulkExiting] = useState(false);
  const bulkCountRef = useRef(0);

  const stopSelecting = () => {
    setSelectMode(false);
    setSelected(new Set());
    setMenuId(null);
  };

  useEffect(() => {
    setSelected(new Set());
    setSelectMode(false);
    setMenuId(null);
  }, [listState, filter, sourceId]);

  useEffect(() => {
    const ids = new Set(shown.map((n) => n.id));
    setSelected((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (ids.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [shown]);

  useEffect(() => {
    if (!selectMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      setSelectMode(false);
      setSelected(new Set());
      setMenuId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectMode]);

  const showBulk = selectMode && selected.size > 0;
  useEffect(() => {
    if (showBulk) {
      setBulkMounted(true);
      setBulkExiting(false);
      return undefined;
    }
    if (!bulkMounted) return undefined;
    const reduce =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setBulkMounted(false);
      setBulkExiting(false);
      return undefined;
    }
    setBulkExiting(true);
    const t = window.setTimeout(() => {
      setBulkMounted(false);
      setBulkExiting(false);
    }, BULK_BAR_MS);
    return () => window.clearTimeout(t);
  }, [showBulk, bulkMounted]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedIds = [...selected];
  const allShownSelected = shown.length > 0 && selected.size === shown.length;
  const selecting = selectMode;
  if (selected.size > 0) bulkCountRef.current = selected.size;

  const listProps = {
    projectNames,
    selectedIds: selected,
    menuId,
    selecting,
    archivedView: archived,
    density,
    onSelect: onOpen,
    onPin,
    onToggleSelect: selecting ? toggleSelect : undefined,
    onMenu: setMenuId,
    onArchive: (n: Note) => onArchive([n.id], !(n.archived || archived)),
    onExport: (n: Note) => onExport([n.id]),
    onDelete: (n: Note) => setPendingDelete([n.id]),
  };

  const noMatch = !empty && shown.length === 0;
  const filtered = filter !== 'all' || Boolean(query.trim()) || Boolean(sourceId);

  return (
    <>
      <div
        className={`notes-index page-scaffold${compact ? ' is-compact' : ''}${selecting ? ' is-selecting' : ''}`}
      >
        <div className="notes-index-rail">
          <div
            className="notes-rail-seg notes-rail-scope"
            role="tablist"
            aria-label={t('notes:index.scopeAria')}
          >
            <button
              type="button"
              role="tab"
              className={listState === 'active' ? 'is-on' : ''}
              aria-selected={listState === 'active'}
              data-testid="notes-list-state-active"
              onClick={() => onListStateChange('active')}
            >
              {t('notes:state.active')}
            </button>
            <button
              type="button"
              role="tab"
              className={archived ? 'is-on' : ''}
              aria-selected={archived}
              data-testid="notes-list-state-archived"
              onClick={() => onListStateChange('archived')}
            >
              {t('notes:state.archived')}
            </button>
          </div>

          <div className="notes-rail-find">
            <label className="notes-rail-search">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                width={15}
                height={15}
                aria-hidden
              >
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.3-4.3" />
              </svg>
              <input
                id="notes-search-input"
                type="text"
                role="searchbox"
                placeholder={t('notes:index.searchPlaceholder')}
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                autoComplete="off"
                aria-label={t('notes:index.searchAria')}
              />
            </label>

            <GlassSelect
              size="sm"
              className="notes-rail-filter"
              aria-label={t('notes:index.filterAria')}
              value={filter}
              options={NOTES_FILTER_OPTIONS.map((o) => ({
                value: o.value,
                label: t(`notes:${o.label}`),
              }))}
              onChange={(v) => onFilter(v as NotesFilter)}
            />
            <GlassSelect
              size="sm"
              className="notes-rail-order"
              aria-label={t('notes:index.sortAria')}
              value={sort}
              options={NOTES_SORT_OPTIONS.map((o) => ({
                value: o.value,
                label: t(`notes:${o.label}`),
              }))}
              onChange={(v) => onSort(v as NotesSort)}
            />
            {hasProjects ? (
              <GlassSelect
                size="sm"
                className="notes-rail-project"
                aria-label={t('notes:index.projectAria')}
                value={sourceId}
                options={[{ value: '', label: t('notes:index.allProjects') }, ...projectOptions]}
                onChange={onSourceId}
              />
            ) : null}
          </div>

          <div className="notes-rail-tools">
            <div className="notes-rail-cluster" role="group" aria-label={t('notes:index.viewAria')}>
              <div
                className="notes-rail-seg notes-rail-view"
                role="group"
                aria-label={t('notes:index.layoutAria')}
              >
                <button
                  type="button"
                  className={layout === 'list' ? 'is-on' : ''}
                  aria-pressed={layout === 'list'}
                  aria-label={t('notes:layout.list')}
                  title={t('notes:layout.list')}
                  onClick={() => onLayoutChange('list')}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden
                  >
                    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
                  </svg>
                </button>
                <button
                  type="button"
                  className={layout === 'card' ? 'is-on' : ''}
                  aria-pressed={layout === 'card'}
                  aria-label={t('notes:layout.card')}
                  title={t('notes:layout.card')}
                  onClick={() => onLayoutChange('card')}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden
                  >
                    <rect x="3" y="3" width="7" height="7" rx="1" />
                    <rect x="14" y="3" width="7" height="7" rx="1" />
                    <rect x="3" y="14" width="7" height="7" rx="1" />
                    <rect x="14" y="14" width="7" height="7" rx="1" />
                  </svg>
                </button>
              </div>
              <div
                className="notes-rail-seg notes-rail-density"
                role="group"
                aria-label={t('notes:index.densityAria')}
              >
                <button
                  type="button"
                  className={!compact ? 'is-on' : ''}
                  aria-pressed={!compact}
                  data-testid="notes-density-comfortable"
                  onClick={() => onDensity('comfortable')}
                >
                  {t('notes:density.comfortable')}
                </button>
                <button
                  type="button"
                  className={compact ? 'is-on' : ''}
                  aria-pressed={compact}
                  data-testid="notes-density-compact"
                  onClick={() => onDensity('compact')}
                >
                  {t('notes:density.compact')}
                </button>
              </div>
            </div>
            <span className="notes-rail-sep" aria-hidden />
            <div
              className="notes-rail-cluster notes-rail-batch-group"
              role="group"
              aria-label={t('notes:index.batch')}
            >
              <button
                type="button"
                className={`notes-rail-batch${selectMode ? ' is-on' : ''}`}
                aria-pressed={selectMode}
                aria-label={selectMode ? t('notes:index.done') : t('notes:index.batch')}
                data-testid="notes-select-btn"
                onClick={() => (selectMode ? stopSelecting() : setSelectMode(true))}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  width={14}
                  height={14}
                  aria-hidden
                >
                  <rect x="3" y="4" width="4" height="4" rx="1" />
                  <path d="M10 6h11" />
                  <rect x="3" y="10" width="4" height="4" rx="1" />
                  <path d="M10 12h11" />
                  <rect x="3" y="16" width="4" height="4" rx="1" />
                  <path d="M10 18h11" />
                </svg>
                <span className="notes-rail-swap">
                  <span className={selectMode ? 'is-leave' : 'is-here'} aria-hidden={selectMode}>
                    {t('notes:index.batch')}
                  </span>
                  <span className={selectMode ? 'is-here' : 'is-leave'} aria-hidden={!selectMode}>
                    {t('notes:index.done')}
                  </span>
                </span>
              </button>
              <div
                className={`notes-rail-allslot${selectMode ? ' is-open' : ''}`}
                inert={!selectMode}
              >
                <div className="notes-rail-allslot__inner">
                  <button
                    type="button"
                    className="notes-rail-batch notes-rail-all"
                    disabled={!selectMode || busy || shown.length === 0}
                    aria-label={allShownSelected ? t('notes:select.none') : t('notes:select.all')}
                    data-testid="notes-bulk-select-all"
                    onClick={() =>
                      setSelected(allShownSelected ? new Set() : new Set(shown.map((n) => n.id)))
                    }
                  >
                    <span className="notes-rail-swap">
                      <span
                        className={allShownSelected ? 'is-leave' : 'is-here'}
                        aria-hidden={allShownSelected}
                      >
                        {t('notes:select.all')}
                      </span>
                      <span
                        className={allShownSelected ? 'is-here' : 'is-leave'}
                        aria-hidden={!allShownSelected}
                      >
                        {t('notes:select.none')}
                      </span>
                    </span>
                  </button>
                </div>
              </div>
            </div>
            <span className="notes-rail-sep" aria-hidden />
            <div className="notes-rail-cluster notes-rail-actions">
              <NotesAssistButton onClick={onAssist} />
              <button
                type="button"
                className="notes-rail-trash glass-card glass-card--control liquid-glass--pill"
                aria-label={t('notes:trash.title')}
                title={t('notes:trash.title')}
                data-testid="notes-trash-btn"
                onClick={onTrash}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  width={15}
                  height={15}
                  aria-hidden
                >
                  <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
                </svg>
              </button>
              <NotesNewButton onClick={onNew} />
            </div>
          </div>
        </div>

        <div className="page-scaffold__body">
          {bulkMounted ? (
            <div
              className={`notes-bulk${bulkExiting ? ' is-exit' : ''}`}
              role="region"
              aria-label={t('notes:bulk.regionAria')}
              data-testid="notes-bulk-bar"
            >
              <span className="notes-bulk__count" aria-live="polite">
                {t('notes:bulk.countPrefix')}{' '}
                <strong>{selected.size || bulkCountRef.current}</strong>{' '}
                {t('notes:bulk.countSuffix')}
              </span>
              <div className="notes-bulk__actions">
                <button
                  type="button"
                  className="notes-bulk__btn"
                  disabled={busy}
                  data-testid="notes-bulk-archive"
                  onClick={() => onArchive(selectedIds, !archived)}
                >
                  {archived ? t('notes:action.unarchive') : t('notes:action.archive')}
                </button>
                <button
                  type="button"
                  className="notes-bulk__btn"
                  disabled={busy}
                  data-testid="notes-bulk-export"
                  onClick={() => onExport(selectedIds)}
                >
                  {t('notes:action.export')}
                </button>
                <button
                  type="button"
                  className="notes-bulk__btn is-danger"
                  disabled={busy}
                  data-testid="notes-bulk-delete"
                  onClick={() => setPendingDelete(selectedIds)}
                >
                  {t('notes:trash.move')}
                </button>
                <button
                  type="button"
                  className="notes-bulk__btn"
                  disabled={busy}
                  data-testid="notes-bulk-clear"
                  onClick={() => setSelected(new Set())}
                >
                  {t('notes:bulk.clear')}
                </button>
              </div>
            </div>
          ) : null}
          {empty ? (
            <div className="page-scaffold__state">
              <EmptyState
                title={archived ? t('notes:empty.archived') : t('notes:empty.noneYet')}
                icon={EmptyStateIcons.inbox}
                action={
                  archived ? undefined : (
                    <button type="button" className="btn btn-primary" onClick={onNew}>
                      {t('notes:action.new')}
                    </button>
                  )
                }
              />
            </div>
          ) : noMatch ? (
            <div className="page-scaffold__state">
              <EmptyState
                title={filtered ? t('notes:empty.noMatch') : t('notes:empty.none')}
                icon={EmptyStateIcons.inbox}
              />
            </div>
          ) : layout === 'card' ? (
            <div className="notes-grid" data-testid="notes-card-grid">
              <NoteList notes={shown} variant="card" {...listProps} />
            </div>
          ) : (
            <div className="notes-index-list" data-testid="notes-row-list">
              {buckets && buckets.length > 1 ? (
                buckets.map((b) => (
                  <section key={b.id} className="notes-index-bucket">
                    <h3 className="notes-index-bucket__label">{b.label}</h3>
                    <NoteList notes={b.items} variant="list" {...listProps} />
                  </section>
                ))
              ) : (
                <NoteList notes={shown} variant="list" {...listProps} />
              )}
            </div>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={Boolean(pendingDelete?.length)}
        title={t('notes:trash.move')}
        message={
          pendingDelete && pendingDelete.length > 1
            ? t('notes:delete.confirmMany', { n: pendingDelete.length })
            : t('notes:delete.confirm')
        }
        confirmLabel={t('notes:trash.move')}
        danger
        onConfirm={() => {
          if (pendingDelete?.length) onDelete(pendingDelete);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}
