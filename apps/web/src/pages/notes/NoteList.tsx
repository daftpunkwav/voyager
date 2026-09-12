/**
 * @file NoteList
 * @description Renders note items in list or card variant, with pin, selection, and per-item action menu support.
 *
 * Responsibilities:
 * - Render note rows/cards in both densities with snippet, project label,
 *   and updated time
 * - Support pin toggling, batch-selection checkboxes, and the per-item
 *   action menu (archive / export / delete)
 * - Keep keyboard and outside-click dismissal of open menus
 */

import { useEffect, useRef, type KeyboardEvent, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { Note } from '@/api/types';
import { noteSnippet, noteSourceId, noteUpdatedLabel } from './noteListing';
import type { NotesDensity } from './notePrefs';

interface NoteListProps {
  notes: Note[];
  projectNames?: Map<string, string>;
  selectedId?: string | null;
  selectedIds?: Set<string>;
  menuId?: string | null;
  selecting?: boolean;
  archivedView?: boolean;
  onSelect: (note: Note) => void;
  onPin?: (note: Note, pinned: boolean) => void;
  onToggleSelect?: (id: string) => void;
  onMenu?: (id: string | null) => void;
  onArchive?: (note: Note) => void;
  onExport?: (note: Note) => void;
  onDelete?: (note: Note) => void;
  emptyLabel?: string;
  variant?: 'list' | 'card';
  density?: NotesDensity;
}

function PinButton({ pinned, onClick }: { pinned: boolean; onClick: () => void }) {
  const { t } = useTranslation('notes');
  return (
    <button
      type="button"
      className={`note-pin${pinned ? ' is-on' : ''}`}
      aria-label={pinned ? t('notes:pin.remove') : t('notes:pin.add')}
      aria-pressed={pinned}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <svg
        viewBox="0 0 24 24"
        fill={pinned ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="2"
        width={14}
        height={14}
        aria-hidden
      >
        <path d="M12 17v5M8 3h8l-1 7h3l-6 7-6-7h3L8 3z" />
      </svg>
    </button>
  );
}

function NoteItemMenu({
  open,
  archived,
  onOpen,
  onClose,
  onArchive,
  onExport,
  onDelete,
}: {
  open: boolean;
  archived: boolean;
  onOpen: () => void;
  onClose: () => void;
  onArchive: () => void;
  onExport: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation('notes');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, onClose]);

  const stop = (e: MouseEvent) => e.stopPropagation();

  return (
    <div className="note-item-more" ref={ref} onClick={stop} onKeyDown={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`note-more-btn${open ? ' is-on' : ''}`}
        aria-label={t('notes:list.itemMenuAria')}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => (open ? onClose() : onOpen())}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" width={14} height={14} aria-hidden>
          <circle cx="6" cy="12" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="18" cy="12" r="1.6" />
        </svg>
      </button>
      {open ? (
        <div className="notes-more-menu note-item-menu" role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onClose();
              onArchive();
            }}
          >
            {archived ? t('notes:action.unarchive') : t('notes:action.archive')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onClose();
              onExport();
            }}
          >
            {t('notes:action.exportMarkdown')}
          </button>
          <button
            type="button"
            role="menuitem"
            className="is-danger"
            onClick={() => {
              onClose();
              onDelete();
            }}
          >
            {t('notes:trash.move')}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function NoteList({
  notes,
  projectNames,
  selectedId,
  selectedIds,
  menuId,
  selecting = false,
  archivedView = false,
  onSelect,
  onPin,
  onToggleSelect,
  onMenu,
  onArchive,
  onExport,
  onDelete,
  emptyLabel,
  variant = 'list',
  density = 'comfortable',
}: NoteListProps) {
  const { t } = useTranslation('notes');
  const snip = variant === 'card' ? 160 : density === 'compact' ? 72 : 120;
  if (notes.length === 0) {
    return <p className="muted notes-list-empty">{emptyLabel ?? t('notes:list.empty')}</p>;
  }

  return (
    <>
      {notes.map((n) => {
        const src = noteSourceId(n);
        const name = projectNames?.get(src) ?? src;
        const projectLabel = src ? name || t('notes:list.unnamedProject') : '';
        const snippet = noteSnippet(n);
        const time = noteUpdatedLabel(n);
        const pinned = Boolean(n.pinned);
        const archived = Boolean(n.archived) || archivedView;
        const checked = Boolean(selectedIds?.has(n.id));
        const title = n.title || t('notes:untitled');
        const onKey = (e: KeyboardEvent) => {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          e.preventDefault();
          if (selecting && onToggleSelect) onToggleSelect(n.id);
          else onSelect(n);
        };
        const openOrToggle = () => {
          if (selecting && onToggleSelect) onToggleSelect(n.id);
          else onSelect(n);
        };
        const actions =
          onArchive && onExport && onDelete && onMenu ? (
            <NoteItemMenu
              open={menuId === n.id}
              archived={archived}
              onOpen={() => onMenu(n.id)}
              onClose={() => onMenu(null)}
              onArchive={() => onArchive(n)}
              onExport={() => onExport(n)}
              onDelete={() => onDelete(n)}
            />
          ) : null;
        const itemClass = `${variant === 'card' ? 'note-grid-card' : 'note-row'}${selectedId === n.id ? ' active' : ''}${pinned ? ' is-pinned' : ''}${checked ? ' is-selected' : ''}${selecting ? ' is-selecting' : ''}`;

        if (variant === 'card') {
          return (
            <div
              key={n.id}
              role="button"
              tabIndex={0}
              data-testid="note-item"
              className={itemClass}
              aria-pressed={selecting ? checked : undefined}
              onClick={openOrToggle}
              onKeyDown={onKey}
            >
              <div className="note-card-head">
                {projectLabel ? (
                  <span className="project-tag">{projectLabel}</span>
                ) : (
                  <span className="note-card-head__spacer" />
                )}
                {onPin ? <PinButton pinned={pinned} onClick={() => onPin(n, !pinned)} /> : null}
              </div>
              <h4>{title}</h4>
              {snippet ? (
                <p className="snippet">{snippet.slice(0, snip)}</p>
              ) : (
                <p className="snippet muted">{t('notes:list.noSnippet')}</p>
              )}
              <div className="meta">
                <span>{time || t('notes:list.justNow')}</span>
                {actions}
              </div>
            </div>
          );
        }
        return (
          <div
            key={n.id}
            role="button"
            tabIndex={0}
            data-testid="note-item"
            className={itemClass}
            aria-pressed={selecting ? checked : undefined}
            onClick={openOrToggle}
            onKeyDown={onKey}
          >
            {onPin ? (
              <PinButton pinned={pinned} onClick={() => onPin(n, !pinned)} />
            ) : (
              <span className="note-pin-slot" />
            )}
            <div className="note-row-title">{title}</div>
            <div className="note-row-snippet">
              {snippet ? snippet.slice(0, snip) : t('notes:list.noSnippet')}
            </div>
            <div className="note-row-project">{projectLabel || '—'}</div>
            <div className="note-row-time">{time || '—'}</div>
            {actions ?? <span className="note-more-slot" />}
          </div>
        );
      })}
    </>
  );
}
