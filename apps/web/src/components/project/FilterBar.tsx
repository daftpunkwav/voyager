/**
 * @file FilterBar
 * @description Project list filter toolbar: debounced text search plus category/language/progress/tag dropdowns and sorting, backed by projectStore.
 *
 * Responsibilities:
 * - Debounce the text search input before committing it to the project store
 * - Expose category / language / progress / tag dropdowns and the sort control
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Category, Project, Tag } from '@/api/types';
import { useProjectStore } from '@/stores/projectStore';
import { FilterDropdown } from './FilterDropdown';

interface FilterBarProps {
  categories: Category[];
  tags: Tag[];
  languages: string[];
}

export function FilterBar({ categories, tags, languages }: FilterBarProps) {
  const { t } = useTranslation('sources');
  const search = useProjectStore((s) => s.search);
  const setSearch = useProjectStore((s) => s.setSearch);
  const categoryId = useProjectStore((s) => s.categoryId);
  const setCategoryId = useProjectStore((s) => s.setCategoryId);
  const language = useProjectStore((s) => s.language);
  const setLanguage = useProjectStore((s) => s.setLanguage);
  const progress = useProjectStore((s) => s.progress);
  const setProgress = useProjectStore((s) => s.setProgress);
  const tagId = useProjectStore((s) => s.tagId);
  const setTagId = useProjectStore((s) => s.setTagId);
  const sortBy = useProjectStore((s) => s.sortBy);
  const setSortBy = useProjectStore((s) => s.setSortBy);
  const resetFilters = useProjectStore((s) => s.resetFilters);
  const [localSearch, setLocalSearch] = useState(search);

  useEffect(() => {
    const t = setTimeout(() => setSearch(localSearch), 300);
    return () => clearTimeout(t);
  }, [localSearch, setSearch]);

  const langs = useMemo(() => {
    if (languages.length > 0) return languages;
    return [];
  }, [languages]);

  const hasActiveFilter = Boolean(categoryId || language || progress || tagId || localSearch);

  const categoryOptions = useMemo(
    () => [
      { value: '', label: t('sources:all') },
      ...categories.map((c) => ({ value: c.id, label: c.name })),
    ],
    [categories, t]
  );

  const languageOptions = useMemo(
    () => [{ value: '', label: t('sources:all') }, ...langs.map((l) => ({ value: l, label: l }))],
    [langs, t]
  );

  const progressOptions = useMemo(
    () => [
      { value: '', label: t('sources:all') },
      { value: 'none', label: t('sources:progress.none') },
      { value: 'learning', label: t('sources:progress.learning') },
      { value: 'learned', label: t('sources:progress.learned') },
      { value: 'mastered', label: t('sources:progress.mastered') },
    ],
    [t]
  );

  const tagOptions = useMemo(
    () => [
      { value: '', label: t('sources:all') },
      ...tags.map((t) => ({ value: t.id, label: t.name })),
    ],
    [tags, t]
  );

  const sortOptions = useMemo(
    () => [
      { value: 'updated_at', label: t('sources:filter.sort.updated') },
      { value: 'imported_at', label: t('sources:filter.sort.imported') },
      { value: 'stars', label: t('sources:filter.sort.stars') },
      { value: 'name', label: t('sources:filter.sort.name') },
    ],
    [t]
  );

  return (
    <div
      className="filter-bar glass-card glass-card--overview-outer glass-overflow-visible"
      role="toolbar"
      aria-label={t('sources:filter.toolbarAria')}
    >
      <div className="filter-search">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width={14}
          height={14}
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          type="text"
          placeholder={t('sources:filter.searchPlaceholder')}
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
        />
      </div>

      <FilterDropdown
        prefix={t('sources:filter.prefix.category')}
        value={categoryId ?? ''}
        options={categoryOptions}
        onChange={(v) => setCategoryId(v || null)}
        active={Boolean(categoryId)}
        ariaLabel={t('sources:filter.aria.category')}
      />

      <FilterDropdown
        prefix={t('sources:filter.prefix.language')}
        value={language ?? ''}
        options={languageOptions}
        onChange={(v) => setLanguage(v || null)}
        active={Boolean(language)}
        ariaLabel={t('sources:filter.aria.language')}
      />

      <FilterDropdown
        prefix={t('sources:filter.prefix.progress')}
        value={progress ?? ''}
        options={progressOptions}
        onChange={(v) => setProgress((v || null) as Project['progress'] | null)}
        active={Boolean(progress)}
        ariaLabel={t('sources:filter.aria.progress')}
      />

      <FilterDropdown
        prefix={t('sources:filter.prefix.tag')}
        value={tagId ?? ''}
        options={tagOptions}
        onChange={(v) => setTagId(v || null)}
        active={Boolean(tagId)}
        ariaLabel={t('sources:filter.aria.tag')}
      />

      <div className="filter-dropdown filter-dropdown--sort">
        <FilterDropdown
          prefix={t('sources:filter.prefix.sort')}
          value={sortBy}
          options={sortOptions}
          onChange={(v) => setSortBy(v as 'name' | 'stars' | 'imported_at' | 'updated_at')}
          active={sortBy !== 'imported_at'}
          ariaLabel={t('sources:filter.aria.sort')}
        />
      </div>

      {hasActiveFilter && (
        <button type="button" className="filter-clear" onClick={resetFilters}>
          {t('sources:filter.clear')}
        </button>
      )}
    </div>
  );
}
