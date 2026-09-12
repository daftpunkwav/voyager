/**
 * @file provider
 * @description Sources-page awareness: the list page reports the current stream count, detail pages report kind + title.
 *
 * Summaries never embed README/body content. List data lives in react-query and
 * detail titles in component state; pages write into the module cache below and
 * the provider only reads from it.
 *
 * Responsibilities:
 * - Hold the module-level caches: list count (list page) and kind/id/
 *   title detail (repo/doc/web readers)
 * - Report localized index lines; skip reporting while data is not ready
 *   instead of fabricating a count
 */

import type { PageProbe } from '@/bridge/pageContext';
import { i18n } from '@/i18n';

// ---- List page (/sources) ----

/** null = source stream not ready (loading/failed); never reports a false 0. */
let listCount: number | null = null;

export function rememberSourcesListCount(count: number | null): void {
  listCount = count;
}

export function lastSourcesListCount(): number | null {
  return listCount;
}

export const sourcesProvider: PageProbe = {
  page: 'sources',
  report() {
    const n = listCount;
    if (n === null) return null;
    return {
      summary: i18n.t('sources:provider.librarySummary', { count: n }),
      counts: { items: n },
    };
  },
};

// ---- Detail pages (/sources/repo / doc / web/:id) ----

export interface SourceDetail {
  /** repo / doc / web (legacy routes without kind are treated as repo) */
  kind: string;
  id: string;
  /** Empty string until the title arrives; the probe falls back to id */
  title: string;
}

let detail: SourceDetail | null = null;

export function rememberSourceDetail(next: SourceDetail | null): void {
  detail = next;
}

export function lastSourceDetail(): SourceDetail | null {
  return detail;
}

const KIND_KEYS: Record<string, string> = {
  repo: 'repo',
  doc: 'doc',
  web: 'web',
};

export const sourceDetailProvider: PageProbe = {
  // Detail pages belong to the same backend domain (reported page field stays "sources")
  page: 'sources',
  report() {
    const d = detail;
    if (!d) return null;
    const kindLabel = KIND_KEYS[d.kind] ? i18n.t(`sources:kind.${d.kind}`) : d.kind;
    const title = d.title.trim().slice(0, 40);
    return {
      summary: i18n.t('sources:provider.detailSummary', { kind: kindLabel, title: title || d.id }),
      selected: d.id,
    };
  },
};
