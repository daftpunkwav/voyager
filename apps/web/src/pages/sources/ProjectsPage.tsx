/**
 * @file ProjectsPage
 * @description Repo projects page: stats cards, filters, project table, bulk actions, and import entry points.
 *
 * Can render embedded (no page-head) when hosted inside SourcesPage. Initial
 * load and failure render a centered spinner / error state instead of a
 * half-built page shell.
 *
 * Responsibilities:
 * - Render stats cards, the filter bar (search / category / language /
 *   progress / tag / sort), and the project table
 * - Run bulk delete and mark-learning with confirmations, and manage the
 *   category/tag manager plus import drawers
 * - Render standalone or embedded (no page-head) depending on the host
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  useCategories,
  useBulkDeleteProjects,
  useBulkMarkLearning,
  useProjects,
  useProjectStats,
  useTags,
} from '@/hooks/useProjects';
import { useProjectStore } from '@/stores/projectStore';
import { useUIStore } from '@/stores/uiStore';
import { FilterBar } from '@/components/project/FilterBar';
import { useProjectLanguages } from '@/hooks/useProjects';
import { ProjectTable } from '@/components/project/ProjectTable';
import { ImportStarsDrawer } from '@/components/project/ImportStarsDrawer';
import { ImportUrlsModal } from '@/components/project/ImportUrlsModal';
import { CategoryTagManager } from '@/components/project/CategoryTagManager';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { backendUnreachable } from '@/utils/errors';
import { abbrevCount } from '@/utils/format';
import { GLASS_OUTER } from '@/constants/glassTokens';

const STAT_ICONS = {
  total: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width={16}
      height={16}
    >
      <path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" />
      <path d="M3 7l9 4 9-4" />
    </svg>
  ),
  mastered: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width={16}
      height={16}
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  learning: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width={16}
      height={16}
    >
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  ),
  none: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width={16}
      height={16}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
};

export function ProjectsPage({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation('sources');
  const { data, isLoading, isError, error, refetch } = useProjects();
  const { data: categories = [] } = useCategories();
  const { data: tags = [] } = useTags();
  const { data: stats } = useProjectStats();
  const page = useProjectStore((s) => s.page);
  const pageSize = useProjectStore((s) => s.pageSize);
  const setPage = useProjectStore((s) => s.setPage);
  const selectedIds = useProjectStore((s) => s.selectedIds);
  const clearSelected = useProjectStore((s) => s.clearSelected);
  const deleteMutation = useBulkDeleteProjects();
  const updateProgress = useBulkMarkLearning();
  const addToast = useUIStore((s) => s.addToast);
  const [starsOpen, setStarsOpen] = useState(false);
  const [urlsOpen, setUrlsOpen] = useState(false);
  const [mgrOpen, setMgrOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [bulkPending, setBulkPending] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) useProjectStore.getState().setSearch(q);
    if (searchParams.get('import') === 'stars') setStarsOpen(true);
  }, [searchParams]);

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;
  const byP = stats?.by_progress;

  const languages = useProjectLanguages(data?.items ?? []);

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    setBulkPending(true);
    // The bulk mutation chunks work and runs it concurrently; the failed count comes back with the result (a mid-way failure does not abort the rest)
    const { failed } = await deleteMutation.mutateAsync([...selectedIds]);
    setBulkPending(false);
    setConfirmDelete(false);
    const succeeded = selectedIds.length - failed;
    if (failed === 0) {
      addToast({ type: 'success', message: t('sources:projects.deleted', { count: succeeded }) });
    } else {
      addToast({
        type: failed === selectedIds.length ? 'error' : 'warning',
        message: t('sources:projects.deletePartial', { ok: succeeded, failed }),
      });
    }
    clearSelected();
  };

  const handleBulkMarkLearning = async () => {
    if (selectedIds.length === 0) return;
    setBulkPending(true);
    const { failed } = await updateProgress.mutateAsync([...selectedIds]);
    setBulkPending(false);
    addToast({
      type: failed === 0 ? 'success' : 'warning',
      message:
        t('sources:projects.markLearningDone', { count: selectedIds.length - failed }) +
        (failed > 0 ? t('sources:projects.markLearningFailSuffix', { count: failed }) : ''),
    });
    clearSelected();
  };

  // Do not render a half-built page shell on first load or failure
  // (title + filter bar + dangling stat cards); match other pages with a
  // centered loading indicator or error state + retry.
  if (isLoading) {
    return (
      <div className="page-scaffold projects-page">
        <div className="page-scaffold__state">
          <LoadingSpinner label={t('sources:projects.loading')} />
        </div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="page-scaffold projects-page">
        <div className="page-scaffold__state">
          <EmptyState
            title={t('sources:projects.loadFailedTitle')}
            description={error instanceof Error ? error.message : backendUnreachable()}
            icon={EmptyStateIcons.library}
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  return (
    <>
      {!embedded && (
        <div className="page-head">
          <div className="actions">
            <button
              type="button"
              className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
              onClick={() => setMgrOpen(true)}
            >
              {t('sources:projects.btnCategories')}
            </button>
            <button
              type="button"
              className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
              data-testid="import-stars-btn"
              onClick={() => setStarsOpen(true)}
            >
              <span className="gh-dot" />
              {t('sources:projects.btnGithubSync')}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setUrlsOpen(true)}>
              {t('sources:projects.btnImport')}
            </button>
          </div>
        </div>
      )}

      {stats && (
        <section className="stat-grid" data-testid="stats-cards">
          <article className={`stat-card ${GLASS_OUTER}`}>
            <div className="stat-icon">{STAT_ICONS.total}</div>
            <div className="stat-label">{t('sources:projects.statsTotal')}</div>
            <div className="stat-value">{stats.total}</div>
            <div className="stat-delta" style={{ color: 'var(--text-500)' }}>
              {t('sources:projects.statsActive')}
            </div>
          </article>
          <article className={`stat-card stat-green ${GLASS_OUTER}`}>
            <div className="stat-icon">{STAT_ICONS.mastered}</div>
            <div className="stat-label">{t('sources:progress.mastered')}</div>
            <div className="stat-value">{byP?.mastered ?? 0}</div>
            <div className="stat-delta">
              {stats.total ? Math.round(((byP?.mastered ?? 0) / stats.total) * 100) : 0}%
              {t('sources:projects.shareSuffix')}
            </div>
          </article>
          <article className={`stat-card stat-orange ${GLASS_OUTER}`}>
            <div className="stat-icon">{STAT_ICONS.learning}</div>
            <div className="stat-label">{t('sources:progress.learning')}</div>
            <div className="stat-value">{byP?.learning ?? 0}</div>
            <div className="stat-delta">
              {stats.total ? Math.round(((byP?.learning ?? 0) / stats.total) * 100) : 0}%
              {t('sources:projects.shareSuffix')}
            </div>
          </article>
          <article className={`stat-card stat-purple ${GLASS_OUTER}`}>
            <div className="stat-icon">{STAT_ICONS.none}</div>
            <div className="stat-label">{t('sources:progress.none')}</div>
            <div className="stat-value">{byP?.none ?? 0}</div>
            <div className="stat-delta" style={{ color: 'var(--text-500)' }}>
              {stats.total ? Math.round(((byP?.none ?? 0) / stats.total) * 100) : 0}%
              {t('sources:projects.shareSuffix')}
            </div>
          </article>
        </section>
      )}

      <FilterBar categories={categories} tags={tags} languages={languages} />

      {selectedIds.length > 0 && (
        <div
          className="bulk-bar"
          role="region"
          aria-label={t('sources:projects.bulkAria')}
          data-testid="bulk-bar"
        >
          <span className="bulk-bar__count">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width={14}
              height={14}
            >
              <path d="M20 6L9 17l-5-5" />
            </svg>
            {t('sources:projects.selectedPrefix')}
            <strong>{selectedIds.length}</strong>
            {t('sources:projects.selectedSuffix')}
          </span>
          <div className="bulk-bar__actions">
            <button
              type="button"
              className="bulk-bar__btn"
              onClick={() => void handleBulkMarkLearning()}
              disabled={bulkPending}
              data-testid="bulk-mark-learning-btn"
            >
              {t('sources:projects.btnMarkLearning')}
            </button>
            <button
              type="button"
              className="bulk-bar__btn bulk-bar__btn--danger"
              onClick={() => setConfirmDelete(true)}
              disabled={bulkPending}
              data-testid="bulk-delete-btn"
            >
              {t('sources:projects.btnDeleteSelected')}
            </button>
            <button
              type="button"
              className="bulk-bar__btn"
              onClick={clearSelected}
              disabled={bulkPending}
              data-testid="bulk-clear-btn"
            >
              {t('sources:projects.btnClearSelection')}
            </button>
          </div>
        </div>
      )}

      <ProjectTable
        projects={data?.items ?? []}
        tags={tags}
        categories={categories}
        onImportClick={() => setStarsOpen(true)}
      />
      {data && data.items.length > 0 && (
        <div className="pagination">
          <span className="info">
            {t('sources:projects.pageInfo', {
              page,
              total: totalPages,
              count: abbrevCount(data.total),
            })}
          </span>
          <div className="pages">
            <button
              type="button"
              className="page-btn"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              aria-label={t('sources:prevPage')}
            >
              ‹
            </button>
            <button type="button" className="page-btn active" aria-current="page">
              {page}
            </button>
            <button
              type="button"
              className="page-btn"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              aria-label={t('sources:nextPage')}
            >
              ›
            </button>
          </div>
        </div>
      )}

      <ImportStarsDrawer open={starsOpen} onClose={() => setStarsOpen(false)} />
      <ImportUrlsModal open={urlsOpen} onClose={() => setUrlsOpen(false)} />
      <CategoryTagManager
        open={mgrOpen}
        onClose={() => setMgrOpen(false)}
        categories={categories}
        tags={tags}
      />

      <ConfirmDialog
        open={confirmDelete}
        title={t('sources:projects.deleteCountTitle', { count: selectedIds.length })}
        message={t('sources:projects.deleteMessage')}
        confirmLabel={t('sources:projects.confirmDelete')}
        cancelLabel={t('sources:cancel')}
        danger
        onConfirm={() => void handleBulkDelete()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
