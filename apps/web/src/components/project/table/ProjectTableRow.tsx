/**
 * @file ProjectTableRow
 * @description One project row of the project table: repo cell, category
 * badge, language, stars, progress pill, tags and the row action.
 *
 * Responsibilities:
 * - Render the project's cells (repo, category, language, stars, progress, tags)
 * - Toggle the row's selection without triggering the row navigation
 * - Open the repo detail route when the row or its action is used
 *
 * Constraints:
 * - Presentation only: the selection state arrives through props and the
 *   toggle is reported back to the table.
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { Category, Project } from '@/api/types';
import { ProgressBadge } from '@/components/project/ProgressBadge';
import { categoryCssClass, categoryLabel } from '@/utils/labels';
import { abbrevCount, langCssClass, REPO_AVATAR_GRADIENTS, repoDisplayParts } from '@/utils/format';
import { routes } from '@/utils/routes';

export function ProjectTableRow({
  project,
  index,
  categories,
  tagMap,
  selected,
  onToggleSelected,
}: {
  project: Project;
  /** Row position on the page; picks the repo avatar gradient. */
  index: number;
  categories: Category[];
  /** Tag id -> display name, resolved by the table. */
  tagMap: Map<string, string>;
  selected: boolean;
  onToggleSelected: (id: string) => void;
}) {
  const { t } = useTranslation('sources');
  const navigate = useNavigate();
  const { owner, repo } = repoDisplayParts(project);
  const catCls = categoryCssClass(project.category, categories);
  return (
    <tr
      data-project-id={project.id}
      data-testid={`project-row-${project.id}`}
      className={selected ? 'is-selected' : undefined}
      onClick={() => {
        void navigate(routes.sourceRepo(project.id));
      }}
    >
      <td className="col-check" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="checkbox"
          aria-label={t('sources:table.rowSelectAria', { name: project.name })}
          data-testid={`projects-row-check-${project.id}`}
          checked={selected}
          onChange={() => onToggleSelected(project.id)}
        />
      </td>
      <td>
        <div className="repo-cell">
          <div
            className="repo-avatar"
            style={{
              background: REPO_AVATAR_GRADIENTS[index % REPO_AVATAR_GRADIENTS.length],
            }}
          >
            {(repo[0] ?? '?').toUpperCase()}
          </div>
          <div className="repo-info">
            <div className="repo-name">
              {owner ? (
                <>
                  <span className="owner">{owner}</span>
                  <span className="slash">/</span>
                </>
              ) : null}
              <span>{repo}</span>
            </div>
            <div className="repo-desc">{project.description ?? ''}</div>
          </div>
        </div>
      </td>
      <td>
        <span className={`badge ${catCls}`}>{categoryLabel(project.category, categories)}</span>
      </td>
      <td>
        <span className={`lang-dot ${langCssClass(project.language)}`}>
          {project.language ?? '-'}
        </span>
      </td>
      <td>
        <span className="stars">★ {abbrevCount(project.stars)}</span>
      </td>
      <td>
        <ProgressBadge progress={project.progress} />
      </td>
      <td>
        <div className="tags">
          {project.tags?.slice(0, 2).map((tid) => (
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
            onClick={() => {
              void navigate(routes.sourceRepo(project.id));
            }}
          >
            {t('sources:table.view')}
          </button>
        </div>
      </td>
    </tr>
  );
}
