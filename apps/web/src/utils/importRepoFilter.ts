/**
 * @file importRepoFilter
 * @description Client-side filtering and sorting for the import / Stars sync list.
 *
 * Responsibilities:
 * - Filter starred/search results by keyword, language, and import status
 * - Sort by stars/name/language with deterministic tie-breaking
 * - Collect the language facet and count imported/not-imported items
 *
 * This module must not depend on UI-layer components.
 */

import type { StarRepo } from '@/api/types';

/** Import status filter. */
export type ImportStatusFilter = 'all' | 'not_imported' | 'imported';

/** Sort key. */
export type ImportSortBy = 'stars' | 'name' | 'language';

export interface ImportRepoFilterState {
  /** Keyword matched against owner/repo/description (case-insensitive). */
  query: string;
  /** Language; empty string means all. */
  language: string;
  /** Whether the repo has been imported. */
  importStatus: ImportStatusFilter;
  sortBy: ImportSortBy;
}

export const DEFAULT_IMPORT_REPO_FILTER: ImportRepoFilterState = {
  query: '',
  language: '',
  // Exclude already-imported repos by default to reduce noise
  importStatus: 'not_imported',
  sortBy: 'stars',
};

export function collectRepoLanguages(items: StarRepo[]): string[] {
  const set = new Set<string>();
  for (const item of items) {
    const lang = item.language?.trim();
    if (lang) set.add(lang);
  }
  return [...set].sort((a, b) => a.localeCompare(b, 'en'));
}

function matchesQuery(item: StarRepo, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    item.owner,
    item.repo,
    `${item.owner}/${item.repo}`,
    item.description ?? '',
    item.url,
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

function matchesImportStatus(item: StarRepo, status: ImportStatusFilter): boolean {
  if (status === 'all') return true;
  if (status === 'not_imported') return !item.already_imported;
  return Boolean(item.already_imported);
}

function compareRepos(a: StarRepo, b: StarRepo, sortBy: ImportSortBy): number {
  if (sortBy === 'name') {
    const an = `${a.owner}/${a.repo}`.toLowerCase();
    const bn = `${b.owner}/${b.repo}`.toLowerCase();
    return an.localeCompare(bn, 'en');
  }
  if (sortBy === 'language') {
    const al = (a.language || '\uffff').toLowerCase();
    const bl = (b.language || '\uffff').toLowerCase();
    const byLang = al.localeCompare(bl, 'en');
    if (byLang !== 0) return byLang;
    return (b.stars ?? 0) - (a.stars ?? 0);
  }
  // Stars descending; ties broken by name
  const byStars = (b.stars ?? 0) - (a.stars ?? 0);
  if (byStars !== 0) return byStars;
  return `${a.owner}/${a.repo}`.localeCompare(`${b.owner}/${b.repo}`, 'en');
}

/** Filter and sort the starred / search result list. */
export function filterAndSortStarRepos(
  items: StarRepo[],
  filters: ImportRepoFilterState
): StarRepo[] {
  const language = filters.language.trim();
  const filtered = items.filter((item) => {
    if (!matchesImportStatus(item, filters.importStatus)) return false;
    if (language && (item.language || '') !== language) return false;
    if (!matchesQuery(item, filters.query)) return false;
    return true;
  });
  return filtered.slice().sort((a, b) => compareRepos(a, b, filters.sortBy));
}

/** Count imported / not-imported items in the raw list. */
export function countImportStatus(items: StarRepo[]): {
  total: number;
  imported: number;
  notImported: number;
} {
  let imported = 0;
  for (const item of items) {
    if (item.already_imported) imported += 1;
  }
  return {
    total: items.length,
    imported,
    notImported: items.length - imported,
  };
}
