/**
 * @file ImportStarsDrawer
 * @description Drawer for syncing GitHub Stars: filter and select repos on the left while an embedded agent suggests selections on the right.
 *
 * already_imported is derived locally from the imported project names (the raw
 * stars payload carries no such flag); the selection is pruned whenever filters
 * change so repos that are no longer visible, or already imported, drop out.
 *
 * Responsibilities:
 * - Load and refresh the GitHub Stars list for the stored username
 * - Filter and select repos, pruning selections as filters change
 * - Import the selected repos via the import mutations
 * - Host the embedded agent panel beside the repo list
 */

import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { StarRepo } from '@/api/types';
import { useGithubStars } from '@/hooks/useGithub';
import { useImportProjects, useProjects } from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import {
  collectRepoLanguages,
  countImportStatus,
  DEFAULT_IMPORT_REPO_FILTER,
  filterAndSortStarRepos,
  type ImportRepoFilterState,
} from '@/utils/importRepoFilter';
import { ImportAgentModal } from './ImportAgentModal';
import { ImportRepoFilterBar } from './ImportRepoFilterBar';
import { EmbedAgentChat } from '@/widgets/chat/EmbedAgentChat';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { formatDateTime } from '@/i18n';
import { STORAGE, migrateKey } from '@/brand';

migrateKey(STORAGE.githubUsername, STORAGE.legacy.githubUsername);

interface ImportStarsDrawerProps {
  open: boolean;
  onClose: () => void;
}

function repoKey(s: Pick<StarRepo, 'owner' | 'repo'>): string {
  return `${s.owner}/${s.repo}`;
}

export function ImportStarsDrawer({ open, onClose }: ImportStarsDrawerProps) {
  const { t } = useTranslation('sources');
  const qc = useQueryClient();
  const [ghUser, setGhUser] = useState(() => localStorage.getItem(STORAGE.githubUsername) ?? '');
  const {
    data: starsResult,
    isLoading,
    isFetching,
  } = useGithubStars({
    username: ghUser,
    enabled: open && Boolean(ghUser),
  });
  const { data: projectsPage } = useProjects();
  const importMutation = useImportProjects();
  const addToast = useUIStore((s) => s.addToast);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState<ImportRepoFilterState>(DEFAULT_IMPORT_REPO_FILTER);

  // Wrap the fallback empty array in useMemo so each render does not produce a new reference that destabilizes downstream memo dependencies;
  // already_imported is merged in from locally imported project names (the raw stars data has no such flag)
  const importedNames = useMemo(
    () => new Set((projectsPage?.items ?? []).map((p) => p.name)),
    [projectsPage?.items]
  );
  const stars = useMemo(
    () =>
      (starsResult?.items ?? []).map((s) => ({
        ...s,
        language: s.language ?? null,
        already_imported: importedNames.has(s.repo),
      })),
    [starsResult?.items, importedNames]
  );

  const filteredStars = useMemo(() => filterAndSortStarRepos(stars, filters), [stars, filters]);

  const languages = useMemo(() => collectRepoLanguages(stars), [stars]);
  const statusCounts = useMemo(() => countImportStatus(stars), [stars]);

  const selectableVisible = useMemo(
    () => filteredStars.filter((s) => !s.already_imported),
    [filteredStars]
  );

  useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setFilters(DEFAULT_IMPORT_REPO_FILTER);
    }
  }, [open]);

  // After filters change, drop selections that are no longer visible or already imported, keeping "N selected" in sync with the list
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const visibleKeys = new Set(selectableVisible.map(repoKey));
      let changed = false;
      const next = new Set<string>();
      for (const k of prev) {
        if (visibleKeys.has(k)) next.add(k);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [selectableVisible]);

  const repoKeys = useMemo(() => selectableVisible.map(repoKey), [selectableVisible]);

  const availableRepos = useMemo(
    () =>
      stars.map((s) => ({
        key: repoKey(s),
        language: s.language,
        stars: s.stars,
        already_imported: s.already_imported,
        description: s.description,
      })),
    [stars]
  );

  const importedProjects = useMemo(
    () =>
      (projectsPage?.items ?? []).map((p) => ({
        name: p.name,
        language: p.language,
        progress: p.progress,
        stars: p.stars,
        description: p.description,
      })),
    [projectsPage]
  );

  const filterSummary = useMemo(() => {
    const parts = [
      t('sources:importUrls.filter.show', { count: filteredStars.length }),
      t('sources:importUrls.filter.total', { count: statusCounts.total }),
      t('sources:importUrls.filter.notImported', { count: statusCounts.notImported }),
      t('sources:importUrls.filter.imported', { count: statusCounts.imported }),
    ];
    return parts.join(' · ');
  }, [filteredStars.length, statusCounts, t]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectVisible = () => {
    setSelected(new Set(selectableVisible.map(repoKey)));
  };

  const clearSelection = () => setSelected(new Set());

  const handleImport = async () => {
    const repos = stars
      .filter((s) => selected.has(repoKey(s)) && !s.already_imported)
      .map((s) => ({ owner: s.owner, repo: s.repo, url: s.url }));
    if (repos.length === 0) {
      addToast({ type: 'warning', message: t('sources:stars.selectFirst') });
      return;
    }
    try {
      const result = await importMutation.mutateAsync(repos);
      addToast({ type: 'success', message: result.summary });
      onClose();
    } catch {
      addToast({ type: 'error', message: t('sources:import.failed') });
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      // api/auth.listStars returns {items,total} directly (the envelope is already unwrapped in the api layer)
      const { listStars } = await import('@/api/auth');
      const res = await listStars(ghUser);
      const total = res.total ?? res.items?.length ?? 0;
      void qc.invalidateQueries({ queryKey: ['githubStars', ghUser] });
      addToast({
        type: 'success',
        message: t('sources:stars.refreshed', { count: total }),
      });
    } catch {
      addToast({ type: 'error', message: t('sources:stars.refreshFailed') });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <ImportAgentModal
      open={open}
      onClose={onClose}
      title={t('sources:stars.title')}
      subtitle={t('sources:stars.subtitle')}
      agentPanel={
        <EmbedAgentChat
          mode="import"
          title={t('sources:importUrls.agentTitle')}
          subtitle={t('sources:importUrls.agentSubtitle')}
          agentInitial="C"
          agentClassName="agent-organizer"
          importContext={{
            mode: 'stars',
            available_repo_keys: repoKeys,
            selected_repo_keys: [...selected],
            available_repos: availableRepos,
            imported_projects: importedProjects,
          }}
        />
      }
    >
      {!ghUser ? (
        <div className="import-biz-empty">
          <p>{t('sources:stars.intro')}</p>
          <div className="import-biz-username">
            <input
              value={ghUser}
              placeholder={t('sources:stars.usernamePlaceholder')}
              onChange={(e) => setGhUser(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && ghUser.trim()) {
                  localStorage.setItem(STORAGE.githubUsername, ghUser.trim());
                  setGhUser(ghUser.trim());
                }
              }}
            />
            <button
              type="button"
              className="btn btn-primary"
              disabled={!ghUser.trim()}
              onClick={() => localStorage.setItem(STORAGE.githubUsername, ghUser.trim())}
            >
              {t('sources:stars.sync')}
            </button>
          </div>
        </div>
      ) : isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="import-biz-layout">
          <div className="import-biz-toolbar">
            <div className="import-biz-meta">
              <span className="muted">
                {t('sources:stars.starCount', { count: starsResult?.total ?? stars.length })}
                {starsResult?.cached ? t('sources:stars.cached') : t('sources:stars.live')}
              </span>
              {starsResult?.fetched_at && (
                <span className="muted small">
                  {t('sources:stars.updatedAt', { time: formatDateTime(starsResult.fetched_at) })}
                </span>
              )}
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={isFetching || refreshing}
              onClick={() => void handleRefresh()}
            >
              {refreshing || isFetching ? t('sources:refreshing') : t('sources:stars.forceRefresh')}
            </button>
          </div>

          <ImportRepoFilterBar
            value={filters}
            onChange={setFilters}
            languages={languages}
            summary={filterSummary}
            onSelectVisible={selectVisible}
            onClearSelection={clearSelection}
            selectVisibleDisabled={selectableVisible.length === 0}
            clearSelectionDisabled={selected.size === 0}
          />

          <ul className="import-repo-list import-repo-list--fill">
            {filteredStars.length === 0 ? (
              <li className="import-repo-empty">
                {stars.length === 0 ? t('sources:stars.empty') : t('sources:stars.filteredEmpty')}
              </li>
            ) : (
              filteredStars.map((s: StarRepo) => {
                const key = repoKey(s);
                const isOn = selected.has(key);
                return (
                  <li
                    key={key}
                    className={`import-repo-item ${isOn ? 'import-repo-item--selected' : ''}`}
                  >
                    <label>
                      <input
                        type="checkbox"
                        disabled={s.already_imported}
                        checked={isOn}
                        onChange={() => toggle(key)}
                      />
                      <span className="font-mono">{key}</span>
                      {s.language && <span className="badge">{s.language}</span>}
                      {typeof s.stars === 'number' && s.stars > 0 && (
                        <span className="import-repo-stars">★ {s.stars}</span>
                      )}
                      {s.already_imported && (
                        <span className="badge">{t('sources:importUrls.badgeImported')}</span>
                      )}
                      {s.description && <span className="import-repo-desc">{s.description}</span>}
                    </label>
                  </li>
                );
              })
            )}
          </ul>
          <div className="import-biz-footer">
            <span className="muted">
              {t('sources:importUrls.footerSelected', { count: selected.size })}
            </span>
            <button
              type="button"
              className="btn btn-primary"
              disabled={importMutation.isPending || selected.size === 0}
              onClick={() => void handleImport()}
            >
              {importMutation.isPending
                ? t('sources:importUrls.importing')
                : t('sources:importUrls.importSelected', { count: selected.size })}
            </button>
          </div>
        </div>
      )}
    </ImportAgentModal>
  );
}
