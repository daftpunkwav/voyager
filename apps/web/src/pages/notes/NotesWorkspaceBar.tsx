/**
 * @file NotesWorkspaceBar
 * @description Notes workspace top bar: view modes, font size, project link, save state, and the "more" menu. Presentational only; never calls capabilities directly.
 *
 * Responsibilities:
 * - Render view-mode select, font-size steppers (clamped to the allowed
 *   range), project link, sync-scroll and TOC toggles, and save state
 * - Host the rail actions and the "more" menu (pin / archive / versions /
 *   export / delete / trash), raising every action to the page
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassSelect } from '@/components/common/GlassSelect';
import { NotesAssistButton, NotesNewButton } from './NotesRailActions';
import { NOTES_FONT_MAX, NOTES_FONT_MIN, type NotesMode } from './notePrefs';

interface NotesWorkspaceBarProps {
  mode: NotesMode;
  fontSize: number;
  saveState: 'saved' | 'unsaved' | 'saving';
  persisted: boolean;
  pinned: boolean;
  archived: boolean;
  projectId: string;
  projectOptions: { value: string; label: string }[];
  syncScroll: boolean;
  hasToc: boolean;
  tocOpen: boolean;
  onBack: () => void;
  onNew: () => void;
  onMode: (mode: NotesMode) => void;
  onBumpFont: (delta: number) => void;
  onProject: (id: string) => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
  onToggleSync: () => void;
  onToggleToc: () => void;
  onAssist: () => void;
  onVersions: () => void;
  onExport: () => void;
  onDelete: () => void;
  onTrash: () => void;
}

export function NotesWorkspaceBar({
  mode,
  fontSize,
  saveState,
  persisted,
  pinned,
  archived,
  projectId,
  projectOptions,
  syncScroll,
  hasToc,
  tocOpen,
  onBack,
  onNew,
  onMode,
  onBumpFont,
  onProject,
  onTogglePin,
  onToggleArchive,
  onToggleSync,
  onToggleToc,
  onAssist,
  onVersions,
  onExport,
  onDelete,
  onTrash,
}: NotesWorkspaceBarProps) {
  const { t } = useTranslation('notes');
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!moreOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  return (
    <header className="notes-topbar">
      <button
        type="button"
        className="topbar-action"
        aria-label={t('notes:bar.back')}
        onClick={onBack}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width={16}
          height={16}
          aria-hidden
        >
          <path d="M15 6l-6 6 6 6" />
        </svg>
      </button>
      <div className="view-toggle" role="group" aria-label={t('notes:bar.modeAria')}>
        {(['edit', 'preview', 'split'] as const).map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`notes-mode-${m}`}
            className={`view-btn${mode === m ? ' active' : ''}`}
            aria-pressed={mode === m}
            onClick={() => onMode(m)}
          >
            {m === 'edit'
              ? t('notes:mode.edit')
              : m === 'preview'
                ? t('notes:mode.preview')
                : t('notes:mode.split')}
          </button>
        ))}
        <span className="view-toggle__rule" aria-hidden />
        <button
          type="button"
          className={`view-btn${mode === 'split' && syncScroll ? ' active' : ''}`}
          data-testid="notes-sync-scroll"
          aria-pressed={mode === 'split' && syncScroll}
          aria-label={t('notes:sync.title')}
          title={mode === 'split' ? t('notes:sync.title') : t('notes:sync.disabledHint')}
          disabled={mode !== 'split'}
          onClick={onToggleSync}
        >
          {t('notes:sync.short')}
        </button>
      </div>
      <div
        className="notes-font-ctrl"
        role="group"
        aria-label={t('notes:bar.fontAria')}
        data-testid="notes-font-ctrl"
      >
        <button
          type="button"
          className="notes-font-btn"
          disabled={fontSize <= NOTES_FONT_MIN}
          aria-label={t('notes:font.decrease')}
          onClick={() => onBumpFont(-1)}
        >
          A−
        </button>
        <span className="notes-font-val">{fontSize}</span>
        <button
          type="button"
          className="notes-font-btn"
          disabled={fontSize >= NOTES_FONT_MAX}
          aria-label={t('notes:font.increase')}
          onClick={() => onBumpFont(1)}
        >
          A+
        </button>
      </div>
      {hasToc && (
        <button
          type="button"
          className={`btn btn-sm notes-sync-btn${tocOpen ? ' is-on' : ''}`}
          data-testid="notes-toc-toggle"
          aria-pressed={tocOpen}
          onClick={onToggleToc}
        >
          {t('notes:toc.title')}
        </button>
      )}
      <GlassSelect
        size="sm"
        aria-label={t('notes:bar.projectAria')}
        value={projectId}
        options={[{ value: '', label: t('notes:bar.noProject') }, ...projectOptions]}
        onChange={onProject}
      />
      <div className="notes-topbar-spacer" />
      <div className={`save-indicator ${saveState}`}>
        <span className="dot" />
        <span>
          {saveState === 'saved'
            ? t('notes:save.saved')
            : saveState === 'saving'
              ? t('notes:save.saving')
              : t('notes:save.unsaved')}
        </span>
      </div>
      {persisted && (
        <button
          type="button"
          className={`topbar-action${pinned ? ' is-on' : ''}`}
          aria-pressed={pinned}
          aria-label={pinned ? t('notes:pin.remove') : t('notes:pin.add')}
          data-testid="notes-pin-btn"
          onClick={onTogglePin}
        >
          <svg
            viewBox="0 0 24 24"
            fill={pinned ? 'currentColor' : 'none'}
            stroke="currentColor"
            strokeWidth="2"
            width={16}
            height={16}
            aria-hidden
          >
            <path d="M12 17v5M8 3h8l-1 7h3l-6 7-6-7h3L8 3z" />
          </svg>
        </button>
      )}
      <div className="notes-more" ref={moreRef}>
        <button
          type="button"
          className={`topbar-action${moreOpen ? ' is-on' : ''}`}
          aria-label={t('notes:bar.more')}
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" fill="currentColor" width={16} height={16} aria-hidden>
            <circle cx="6" cy="12" r="1.6" />
            <circle cx="12" cy="12" r="1.6" />
            <circle cx="18" cy="12" r="1.6" />
          </svg>
        </button>
        {moreOpen && (
          <div className="notes-more-menu" role="menu">
            {persisted && (
              <>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMoreOpen(false);
                    onVersions();
                  }}
                >
                  {t('notes:versions.title')}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMoreOpen(false);
                    onExport();
                  }}
                >
                  {t('notes:action.exportMarkdown')}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMoreOpen(false);
                    onToggleArchive();
                  }}
                >
                  {archived ? t('notes:action.unarchive') : t('notes:action.archive')}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="is-danger"
                  onClick={() => {
                    setMoreOpen(false);
                    onDelete();
                  }}
                >
                  {t('notes:trash.move')}
                </button>
              </>
            )}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMoreOpen(false);
                onTrash();
              }}
            >
              {t('notes:trash.title')}
            </button>
          </div>
        )}
      </div>
      <div className="notes-rail-cluster notes-rail-actions">
        <NotesAssistButton onClick={onAssist} />
        <NotesNewButton onClick={onNew} />
      </div>
    </header>
  );
}
