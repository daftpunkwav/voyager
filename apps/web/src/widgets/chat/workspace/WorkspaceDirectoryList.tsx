/**
 * @file WorkspaceDirectoryList
 * @description Listing of the directories inside the workspace chooser: one
 * row per directory entry, plus the empty state for a folder that holds none.
 *
 * Responsibilities:
 * - Render the directory rows of the current listing
 * - Navigate into a directory by reporting its absolute path
 * - Render the empty state for a listing without sub-directories
 *
 * Constraints:
 * - Only directories are listed; files stay out of the chooser.
 * - The rows remain plain buttons: the listbox role belongs to the container.
 */

import { useTranslation } from 'react-i18next';
import type { PickResult } from '@/api/workspace';

export interface WorkspaceDirectoryListProps {
  /** The listing to render; null before the first load settles. */
  current: PickResult | null;
  /** Navigate into a directory path. */
  onEnter: (path: string) => void;
}

/** Directory rows of the current listing. */
export function WorkspaceDirectoryList({ current, onEnter }: WorkspaceDirectoryListProps) {
  const { t } = useTranslation('chat');
  const entries = (current?.entries ?? []).filter((e) => e.type === 'directory');

  return (
    <div className="ws-browser__list" role="listbox" aria-label={t('chat:workspace.browserTitle')}>
      {entries.map((e) => (
        <button
          key={e.name}
          type="button"
          role="option"
          aria-selected={false}
          className="ws-browser__row"
          onClick={() => {
            const next = current?.path
              ? `${current.path.replace(/[\\/]+$/, '')}/${e.name}`
              : e.name;
            onEnter(next);
          }}
        >
          <svg
            className="ws-browser__row-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.9"
            aria-hidden
          >
            <path
              d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="ws-browser__row-name">{e.name}</span>
        </button>
      ))}
      {entries.length === 0 ? (
        <p className="ws-browser__empty">{t('chat:workspace.noDirs')}</p>
      ) : null}
    </div>
  );
}
