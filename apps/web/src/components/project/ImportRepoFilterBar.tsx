/**
 * @file ImportRepoFilterBar
 * @description Filter toolbar for the import / Stars sync list: search, import status, language, sorting, plus selection actions.
 *
 * Responsibilities:
 * - Filter the import list by search, import status, language and sorting
 * - Host selection actions for the currently visible repos
 */

import { useTranslation } from 'react-i18next';
import { GlassSelect } from '@/components/common/GlassSelect';
import {
  type ImportRepoFilterState,
  type ImportSortBy,
  type ImportStatusFilter,
} from '@/utils/importRepoFilter';

interface ImportRepoFilterBarProps {
  value: ImportRepoFilterState;
  onChange: (next: ImportRepoFilterState) => void;
  languages: string[];
  /** Summary text, e.g. "showing 12 / 80 total · 50 not imported" */
  summary?: string;
  /** Select all importable items matching the current filter */
  onSelectVisible?: () => void;
  /** Clear the selection */
  onClearSelection?: () => void;
  selectVisibleDisabled?: boolean;
  clearSelectionDisabled?: boolean;
}

export function ImportRepoFilterBar({
  value,
  onChange,
  languages,
  summary,
  onSelectVisible,
  onClearSelection,
  selectVisibleDisabled,
  clearSelectionDisabled,
}: ImportRepoFilterBarProps) {
  const { t } = useTranslation('sources');

  const STATUS_OPTIONS: Array<{ value: ImportStatusFilter; label: string }> = [
    { value: 'not_imported', label: t('sources:repoFilter.status.notImported') },
    { value: 'imported', label: t('sources:repoFilter.status.imported') },
    { value: 'all', label: t('sources:all') },
  ];

  const SORT_OPTIONS: Array<{ value: ImportSortBy; label: string }> = [
    { value: 'stars', label: t('sources:repoFilter.sort.stars') },
    { value: 'name', label: t('sources:repoFilter.sort.name') },
    { value: 'language', label: t('sources:repoFilter.sort.language') },
  ];

  const languageOptions = [
    { value: '', label: t('sources:repoFilter.allLanguages') },
    ...languages.map((l) => ({ value: l, label: l })),
  ];

  const patch = (partial: Partial<ImportRepoFilterState>) => onChange({ ...value, ...partial });

  return (
    <div className="import-repo-filters">
      <div className="import-repo-filters__row">
        <label className="import-repo-filters__search">
          <input
            type="search"
            className="input"
            aria-label={t('sources:repoFilter.searchAria')}
            placeholder={t('sources:repoFilter.searchPlaceholder')}
            value={value.query}
            onChange={(e) => patch({ query: e.target.value })}
          />
        </label>
        <GlassSelect
          size="sm"
          aria-label={t('sources:repoFilter.aria.status')}
          value={value.importStatus}
          options={STATUS_OPTIONS}
          onChange={(v) => patch({ importStatus: v as ImportStatusFilter })}
        />
        <GlassSelect
          size="sm"
          aria-label={t('sources:repoFilter.aria.language')}
          value={value.language}
          options={languageOptions}
          onChange={(v) => patch({ language: v })}
        />
        <GlassSelect
          size="sm"
          aria-label={t('sources:repoFilter.aria.sort')}
          value={value.sortBy}
          options={SORT_OPTIONS}
          onChange={(v) => patch({ sortBy: v as ImportSortBy })}
        />
      </div>
      <div className="import-repo-filters__meta">
        {summary && <span className="muted small">{summary}</span>}
        <div className="import-repo-filters__actions">
          {onSelectVisible && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={selectVisibleDisabled}
              onClick={onSelectVisible}
            >
              {t('sources:repoFilter.selectVisible')}
            </button>
          )}
          {onClearSelection && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={clearSelectionDisabled}
              onClick={onClearSelection}
            >
              {t('sources:repoFilter.clearSelection')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
