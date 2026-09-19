/**
 * @file ProjectTable
 * @description Project list table with row selection (page-level select-all with indeterminate state), badges, and an empty state.
 *
 * Responsibilities:
 * - Render project rows with category badges, tags and progress pills
 * - Manage page-level selection with a select-all indeterminate checkbox
 * - Navigate to the repo detail route from row actions
 * - Show the shared empty state when no projects match
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { ChangeEvent } from 'react';
import type { Category, Project, Tag } from '@/api/types';
import { ProgressBadge } from './ProgressBadge';
import { categoryCssClass, categoryLabel } from '@/utils/labels';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { abbrevCount, langCssClass, REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { useProjectStore } from '@/stores/projectStore';
import { routes } from '@/utils/routes';

interface ProjectTableProps {
  projects: Project[];
  tags: Tag[];
  categories?: Category[];
  onImportClick?: () => void;
}

export function ProjectTable({
  projects,
  tags,
  categories = [],
  onImportClick,
}: ProjectTableProps) {
  const { t } = useTranslation('sources');
  const navigate = useNavigate();
  const tagMap = new Map(tags.map((t) => [t.id, t.name]));

  const selectedIds = useProjectStore((s) => s.selectedIds);
  const toggleSelected = useProjectStore((s) => s.toggleSelected);
  const setSelected = useProjectStore((s) => s.setSelected);

  const pageIds = projects.map((p) => p.id);
  const selectedSet = new Set(selectedIds);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id));
  const someOnPageSelected = pageIds.some((id) => selectedSet.has(id)) && !allOnPageSelected;

  const handleHeaderToggle = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.checked) {
      // Select all on the current page: merge and dedupe
      const next = new Set(selectedIds);
      pageIds.forEach((id) => next.add(id));
      setSelected(Array.from(next));
    } else {
      // Deselect the current page
      const pageSet = new Set(pageIds);
      setSelected(selectedIds.filter((id) => !pageSet.has(id)));
    }
  };

  if (projects.length === 0) {
    return (
      <div id="table-wrap" data-testid="project-table">
        <EmptyState
          title={t('sources:table.emptyTitle')}
          description={t('sources:table.emptyDesc')}
          icon={EmptyStateIcons.library}
          action={
            <>
              <button
                type="button"
                className="btn btn-primary"
                data-testid="empty-import-stars-btn"
                onClick={onImportClick}
              >
                {t('sources:table.emptySync')}
              </button>
              <button
                type="button"
                className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
                onClick={onImportClick}
              >
                {t('sources:table.emptyPaste')}
              </button>
            </>
          }
        />
      </div>
    );
  }

  return (
    <div id="table-wrap" data-testid="project-table">
      <table className="table">
        <thead>
          <tr>
            <th className="col-check">
              <span className="th-checkbox">
                <input
                  type="checkbox"
                  className="checkbox"
                  aria-label={t('sources:table.selectAllAria')}
                  data-testid="projects-select-all"
                  checked={allOnPageSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someOnPageSelected;
                  }}
                  onChange={handleHeaderToggle}
                />
              </span>
            </th>
            <th>{t('sources:table.col.repo')}</th>
            <th>{t('sources:table.col.category')}</th>
            <th>{t('sources:table.col.language')}</th>
            <th>{t('sources:table.col.stars')}</th>
            <th>{t('sources:table.col.progress')}</th>
            <th>{t('sources:table.col.tags')}</th>
            <th className="col-actions">{t('sources:table.col.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p, i) => {
            const { owner, repo } = splitRepoName(p.name);
            const catCls = categoryCssClass(p.category, categories);
            const isSelected = selectedSet.has(p.id);
            return (
              <tr
                key={p.id}
                data-project-id={p.id}
                data-testid={`project-row-${p.id}`}
                className={isSelected ? 'is-selected' : undefined}
                onClick={() => navigate(routes.sourceRepo(p.id))}
              >
                <td className="col-check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    className="checkbox"
                    aria-label={t('sources:table.rowSelectAria', { name: p.name })}
                    data-testid={`projects-row-check-${p.id}`}
                    checked={isSelected}
                    onChange={() => toggleSelected(p.id)}
                  />
                </td>
                <td>
                  <div className="repo-cell">
                    <div
                      className="repo-avatar"
                      style={{
                        background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length],
                      }}
                    >
                      {(repo[0] ?? '?').toUpperCase()}
                    </div>
                    <div className="repo-info">
                      <div className="repo-name">
                        <span className="owner">{owner}</span>
                        <span className="slash">/</span>
                        <span>{repo}</span>
                      </div>
                      <div className="repo-desc">{p.description ?? ''}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <span className={`badge ${catCls}`}>{categoryLabel(p.category, categories)}</span>
                </td>
                <td>
                  <span className={`lang-dot ${langCssClass(p.language)}`}>
                    {p.language ?? '-'}
                  </span>
                </td>
                <td>
                  <span className="stars">★ {abbrevCount(p.stars)}</span>
                </td>
                <td>
                  <ProgressBadge progress={p.progress} />
                </td>
                <td>
                  <div className="tags">
                    {p.tags?.slice(0, 2).map((tid) => (
                      <span key={tid} className="tag">
                        {tagMap.get(tid) ?? tid.replace(/^tag_/, '')}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="col-actions" onClick={(e) => e.stopPropagation()}>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="btn-scout"
                      onClick={() => navigate(routes.sourceRepo(p.id))}
                    >
                      {t('sources:table.view')}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
