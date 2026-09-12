/**
 * @file SourcesPage
 * @description Sources library page: unified source stream (kind filter) plus the five-in-one import center.
 *
 * The "repo" tab reuses the existing ProjectsPage embedded in place (repo table
 * / filters / bulk actions, same-directory private components); the all / doc /
 * web tabs use the cross-kind list_sources card stream.
 *
 * Responsibilities:
 * - Switch between the embedded repo table and the cross-kind card stream
 * - Keep the stream live via source events and filter it by the shared
 *   search state
 * - Publish the loaded stream count to the page-awareness provider
 */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useSourceEvents, useSourceStream } from '@/hooks/useSources';
import { useProjectStore } from '@/stores/projectStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { backendUnreachable } from '@/utils/errors';
import { ProjectsPage } from './ProjectsPage';
import { ImportCenter, type ImportTab } from './ImportCenter';
import { SourceCard } from './SourceCard';
import { rememberSourcesListCount } from './provider';

type KindTab = '' | 'repo' | 'doc' | 'web';

const TABS: { key: KindTab; labelKey: string }[] = [
  { key: '', labelKey: 'sources:all' },
  { key: 'repo', labelKey: 'sources:kind.repo' },
  { key: 'doc', labelKey: 'sources:kind.doc' },
  { key: 'web', labelKey: 'sources:kind.web' },
];

export function SourcesPage() {
  const { t } = useTranslation('sources');
  const [tab, setTab] = useState<KindTab>('');
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<ImportTab>('files');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) useProjectStore.getState().setSearch(q);
  }, [searchParams]);

  const {
    data: items,
    isLoading,
    isError,
    error,
    refetch,
  } = useSourceStream({
    kind: tab || undefined,
  });
  useSourceEvents();
  const search = useProjectStore((s) => s.search);
  const filtered = useMemo(
    () =>
      items?.filter((r) =>
        search ? r.title.toLowerCase().includes(search.toLowerCase()) : true
      ) ?? [],
    [items, search]
  );

  // Feed the current stream count to the page-awareness provider; skip while loading/failed so a false 0 is never reported
  useEffect(() => {
    if (isLoading || isError) return;
    rememberSourcesListCount(filtered.length);
  }, [filtered.length, isLoading, isError]);

  const openImport = (t: ImportTab) => {
    setImportTab(t);
    setImportOpen(true);
  };

  // Repo tab: the existing repo page takes over entirely (with its own filters/stats/bulk actions)
  if (tab === 'repo') {
    return (
      <div className="page-scaffold sources-page">
        <div className="page-head">
          <KindTabs tab={tab} onChange={setTab} />
          <div className="actions">
            <button
              type="button"
              className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
              onClick={() => openImport('github')}
            >
              {t('sources:importRepos')}
            </button>
          </div>
        </div>
        <ProjectsPage embedded />
        <ImportCenter
          open={importOpen}
          initialTab={importTab}
          onClose={() => setImportOpen(false)}
        />
      </div>
    );
  }

  return (
    <div className="page-scaffold sources-page">
      <div className="page-head">
        <KindTabs tab={tab} onChange={setTab} />
        <div className="actions">
          <button
            type="button"
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            onClick={() => openImport('web')}
          >
            {t('sources:savePage')}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => openImport('files')}>
            {t('sources:importDocs')}
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="page-scaffold__state">
          <LoadingSpinner label={t('sources:list.loading')} />
        </div>
      ) : isError ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('sources:list.loadFailedTitle')}
            description={error instanceof Error ? error.message : backendUnreachable()}
            icon={EmptyStateIcons.library}
            onRetry={() => void refetch()}
          />
        </div>
      ) : filtered.length === 0 ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={search ? t('sources:list.noMatch') : t('sources:list.empty')}
            icon={EmptyStateIcons.library}
            action={
              !search && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => openImport('files')}
                >
                  {t('sources:list.import')}
                </button>
              )
            }
          />
        </div>
      ) : (
        <div className="source-grid" data-testid="source-grid">
          {filtered.map((item) => (
            <SourceCard key={`${item.kind}-${item.id}`} item={item} />
          ))}
        </div>
      )}

      <ImportCenter open={importOpen} initialTab={importTab} onClose={() => setImportOpen(false)} />
    </div>
  );
}

function KindTabs({ tab, onChange }: { tab: KindTab; onChange: (t: KindTab) => void }) {
  const { t } = useTranslation('sources');
  return (
    <nav className="kind-tabs" role="tablist" aria-label={t('sources:list.kindAria')}>
      {TABS.map((tabItem) => (
        <button
          key={tabItem.key}
          type="button"
          role="tab"
          aria-selected={tab === tabItem.key}
          className={`kind-tab ${tab === tabItem.key ? 'is-active' : ''}`}
          onClick={() => onChange(tabItem.key)}
        >
          {t(tabItem.labelKey)}
        </button>
      ))}
    </nav>
  );
}
