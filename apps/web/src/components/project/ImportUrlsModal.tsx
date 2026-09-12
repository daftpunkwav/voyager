/**
 * @file ImportUrlsModal
 * @description Import modal with two tabs: pasting GitHub URLs, or searching GitHub and filtering/selecting repos.
 *
 * The right side hosts an embedded agent that suggests selections; in search mode,
 * selections are pruned whenever filters change so they stay in sync with the list.
 *
 * Responsibilities:
 * - Validate and import pasted GitHub URLs in the paste tab
 * - Search GitHub and filter / select results in the search tab
 * - Prune selections as filters change; host the embedded agent panel
 */

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { searchGithubRepos } from '@/api/projects';
import type { StarRepo } from '@/api/types';
import { useImportProjects, useProjects } from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import { validateGithubUrls } from '@/utils/validators';
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

type ImportTab = 'paste' | 'search';

interface ImportUrlsModalProps {
  open: boolean;
  onClose: () => void;
}

function repoKey(s: Pick<StarRepo, 'owner' | 'repo'>): string {
  return `${s.owner}/${s.repo}`;
}

export function ImportUrlsModal({ open, onClose }: ImportUrlsModalProps) {
  const { t } = useTranslation('sources');
  const [tab, setTab] = useState<ImportTab>('paste');
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<ImportRepoFilterState>(DEFAULT_IMPORT_REPO_FILTER);
  const importMutation = useImportProjects();
  const { data: projectsPage } = useProjects();
  const addToast = useUIStore((s) => s.addToast);

  const { data: searchResults = [], isFetching } = useQuery({
    queryKey: ['githubSearch', search],
    queryFn: async () => (await searchGithubRepos(search)) as StarRepo[],
    enabled: open && tab === 'search' && search.trim().length >= 2,
  });

  const filteredResults = useMemo(
    () => filterAndSortStarRepos(searchResults, filters),
    [searchResults, filters]
  );

  const languages = useMemo(() => collectRepoLanguages(searchResults), [searchResults]);
  const statusCounts = useMemo(() => countImportStatus(searchResults), [searchResults]);

  const selectableVisible = useMemo(
    () => filteredResults.filter((s) => !s.already_imported),
    [filteredResults]
  );

  useEffect(() => {
    if (!open) {
      setText('');
      setSearch('');
      setSelected(new Set());
      setTab('paste');
      setFilters(DEFAULT_IMPORT_REPO_FILTER);
    }
  }, [open]);

  // Prune selections that are no longer visible after filters change
  useEffect(() => {
    if (tab !== 'search') return;
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
  }, [selectableVisible, tab]);

  if (!open) return null;

  const { valid, invalid } = validateGithubUrls(text);

  const filterSummary = [
    t('sources:importUrls.filter.show', { count: filteredResults.length }),
    t('sources:importUrls.filter.total', { count: statusCounts.total }),
    t('sources:importUrls.filter.notImported', { count: statusCounts.notImported }),
    t('sources:importUrls.filter.imported', { count: statusCounts.imported }),
  ].join(' · ');

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

  const importRepos = async (repos: Array<{ owner: string; repo: string; url: string }>) => {
    if (repos.length === 0) {
      addToast({ type: 'warning', message: t('sources:importUrls.selectFirst') });
      return;
    }
    // importProjects submits import_repo per entry; partial failures are disclosed in the response body (ok/failed)
    const result = (await importMutation.mutateAsync(repos)) as {
      ok: number;
      failed: number;
      summary: string;
      errors?: string[];
    };
    if (result.failed > 0) {
      addToast({
        type: 'warning',
        message: t('sources:importUrls.partialFail', {
          summary: result.summary,
          count: result.failed,
        }),
      });
      for (const line of result.errors ?? []) {
        console.warn('[ImportUrlsModal] Failed to import entry:', line);
      }
    } else {
      addToast({ type: 'success', message: result.summary });
    }
    if (result.ok > 0) onClose();
  };

  const handlePasteImport = () =>
    void importRepos(valid.map((v) => ({ owner: v.owner, repo: v.repo, url: v.url })));

  const handleSearchImport = () => {
    const repos = searchResults
      .filter((s) => selected.has(repoKey(s)) && !s.already_imported)
      .map((s) => ({ owner: s.owner, repo: s.repo, url: s.url ?? s.html_url }));
    void importRepos(repos);
  };

  const availableKeys =
    tab === 'search' ? selectableVisible.map(repoKey) : valid.map((v) => v.name);

  const availableRepos =
    tab === 'search'
      ? searchResults.map((s) => ({
          key: repoKey(s),
          language: s.language,
          stars: s.stars,
          already_imported: Boolean(s.already_imported),
          description: s.description,
        }))
      : valid.map((v) => ({
          key: v.name,
          language: null,
          stars: 0,
          already_imported: false,
          description: null,
        }));

  const importedProjects = (projectsPage?.items ?? []).map((p) => ({
    name: p.name,
    language: p.language,
    progress: p.progress,
    stars: p.stars,
    description: p.description,
  }));

  return (
    <ImportAgentModal
      open={open}
      onClose={onClose}
      title={t('sources:importUrls.title')}
      subtitle={t('sources:importUrls.subtitle')}
      size="large"
      agentPanel={
        <EmbedAgentChat
          mode="import"
          title={t('sources:importUrls.agentTitle')}
          subtitle={t('sources:importUrls.agentSubtitle')}
          agentInitial="S"
          agentClassName="agent-recon"
          importContext={{
            mode: tab === 'search' ? 'search' : 'urls',
            available_repo_keys: availableKeys,
            selected_repo_keys: [...selected],
            available_repos: availableRepos,
            imported_projects: importedProjects,
          }}
        />
      }
    >
      <div className="import-biz-layout">
        <div className="import-tabs">
          <button
            type="button"
            className={`import-tab ${tab === 'paste' ? 'active' : ''}`}
            onClick={() => setTab('paste')}
          >
            {t('sources:importUrls.tab.paste')}
          </button>
          <button
            type="button"
            className={`import-tab ${tab === 'search' ? 'active' : ''}`}
            onClick={() => setTab('search')}
          >
            {t('sources:importUrls.tab.search')}
          </button>
        </div>

        {tab === 'paste' ? (
          <>
            <p className="import-hint">{t('sources:importUrls.pasteHint')}</p>
            <textarea
              className="input textarea import-url-textarea"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="https://github.com/owner/repo"
            />
            <p className="import-hint">
              {t('sources:importUrls.validLines', { valid: valid.length, invalid: invalid.length })}
            </p>
            <div className="import-biz-footer">
              <span className="muted">
                {t('sources:importUrls.footerValid', { count: valid.length })}
              </span>
              <button
                type="button"
                className="btn btn-primary"
                disabled={importMutation.isPending || valid.length === 0}
                onClick={handlePasteImport}
              >
                {t('sources:importUrls.confirmImport')}
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="graph-search import-search-field">
              <input
                placeholder={t('sources:importUrls.searchPlaceholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            {isFetching && <p className="muted">{t('sources:importUrls.searching')}</p>}

            {searchResults.length > 0 && (
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
            )}

            <ul className="import-repo-list import-repo-list--fill">
              {search.trim().length < 2 ? (
                <li className="import-repo-empty">{t('sources:importUrls.minChars')}</li>
              ) : isFetching && searchResults.length === 0 ? (
                <li className="import-repo-empty">{t('sources:importUrls.searching')}</li>
              ) : searchResults.length === 0 ? (
                <li className="import-repo-empty">{t('sources:importUrls.noMatch')}</li>
              ) : filteredResults.length === 0 ? (
                <li className="import-repo-empty">{t('sources:importUrls.filteredEmpty')}</li>
              ) : (
                filteredResults.map((s: StarRepo) => {
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
                onClick={handleSearchImport}
              >
                {importMutation.isPending
                  ? t('sources:importUrls.importing')
                  : t('sources:importUrls.importSelected', { count: selected.size })}
              </button>
            </div>
          </>
        )}
      </div>
    </ImportAgentModal>
  );
}
