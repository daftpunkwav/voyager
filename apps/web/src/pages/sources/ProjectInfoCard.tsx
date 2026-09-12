/**
 * @file ProjectInfoCard
 * @description Project detail sidebar card: read-only metadata (URL / category / tags / language) with edit and delete entries.
 *
 * The category renders via categoryLabel(project.category, categories);
 * project.category is a category-name string, not a category_id.
 *
 * Responsibilities:
 * - Render read-only metadata: URL, category label, tags, language, dates
 * - Raise the edit (category/tags dialog) and delete entries to the
 *   coordinator page
 */
import type { Category, Project, Tag } from '@/api/types';
import { useTranslation } from 'react-i18next';
import { categoryLabel } from '@/utils/labels';
import { formatDate } from '@/utils/date';
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';

interface ProjectInfoCardProps {
  project: Project;
  categories: Category[];
  tags: Tag[];
  /** Opens the edit-category-and-tags dialog */
  onEdit: () => void;
  /** Opens the delete-project confirmation dialog */
  onDelete: () => void;
}

/** Project info card: read-only metadata list plus action buttons */
export function ProjectInfoCard({
  project,
  categories,
  tags,
  onEdit,
  onDelete,
}: ProjectInfoCardProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={GLASS_OUTER}>
      <div className="card-header">
        <div className="card-title">{t('sources:info.title')}</div>
        <span className="card-subtitle mono" title={project.id} style={{ fontSize: 11 }}>
          #{project.id.slice(0, 8)}
        </span>
      </div>
      <div className="pd-info-list">
        <div className="pd-info-row">
          <span className="k">URL</span>
          <span className="v">
            <a href={project.url} target="_blank" rel="noopener noreferrer">
              {(project.url ?? '').replace('https://github.com/', '')} ↗
            </a>
          </span>
        </div>
        <div className="pd-info-row">
          <span className="k">{t('sources:info.category')}</span>
          <span className="v">
            <span className="badge">{categoryLabel(project.category, categories)}</span>
          </span>
        </div>
        <div className="pd-info-row">
          <span className="k">{t('sources:info.tags')}</span>
          <span className="v">
            {(project.tags ?? []).length === 0 ? (
              '-'
            ) : (
              <span className="pd-tag-list">
                {(project.tags ?? []).map((tid) => {
                  const name = tags.find((t) => t.id === tid)?.name ?? tid.slice(0, 6);
                  return (
                    <span key={tid} className="badge">
                      {name}
                    </span>
                  );
                })}
              </span>
            )}
          </span>
        </div>
        <div className="pd-info-row">
          <span className="k">{t('sources:info.language')}</span>
          <span className="v">{project.language ?? '-'}</span>
        </div>
        <div className="pd-info-row">
          <span className="k">{t('sources:info.addedAt')}</span>
          <span className="v mono" style={{ fontSize: 12 }}>
            {formatDate(project.imported_at)}
          </span>
        </div>
        <div className="pd-info-row">
          <span className="k">{t('sources:info.source')}</span>
          <span className="v">
            {project.source === 'github'
              ? t('sources:info.sourceGithub')
              : t('sources:info.sourceManual')}
          </span>
        </div>
      </div>
      <div className="pd-info-actions">
        <button type="button" className={`btn btn-block ${GLASS_INNER}`} onClick={onEdit}>
          {t('sources:info.edit')}
        </button>
        <button
          type="button"
          className={`btn btn-block ${GLASS_INNER}`}
          style={{ color: 'var(--error)' }}
          onClick={onDelete}
        >
          {t('sources:info.delete')}
        </button>
      </div>
    </div>
  );
}
