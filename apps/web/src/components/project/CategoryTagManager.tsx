/**
 * @file CategoryTagManager
 * @description Read-only browse panel for categories and tags (project library entry point).
 *
 * In the current model, categories/tags are plain string fields on resources with no
 * global entities, so this panel only browses aggregates (with usage counts);
 * creation and deletion happen in the per-project edit modal.
 *
 * Responsibilities:
 * - Browse category and tag aggregates with usage counts in a read-only modal
 * - Close via overlay click or the header button; render empty hints per list
 */
import { useTranslation } from 'react-i18next';
import type { Category, Tag } from '@/api/types';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface CategoryTagManagerProps {
  open: boolean;
  onClose: () => void;
  categories: Category[];
  tags: Tag[];
}

export function CategoryTagManager({ open, onClose, categories, tags }: CategoryTagManagerProps) {
  const { t } = useTranslation('sources');

  return (
    <ModalOverlay open={open} onClose={onClose}>
      <div
        className="modal modal--wide edit-project-modal glass-card glass-card--dialog glass-overflow-visible"
        role="dialog"
        aria-labelledby="cat-tag-mgr-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="edit-project-modal__head">
          <div>
            <h2 id="cat-tag-mgr-title">{t('sources:mgr.title')}</h2>
            <p className="muted small">{t('sources:mgr.subtitle')}</p>
          </div>
          <button
            type="button"
            className="chat-icon-btn"
            onClick={onClose}
            aria-label={t('sources:closeAria')}
          >
            ×
          </button>
        </header>

        <div className="edit-project-modal__body">
          <span className="label">
            {t('sources:mgr.categoriesLabel', { count: categories.length })}
          </span>
          <ul className="cat-tag-mgr-list">
            {categories.length === 0 && (
              <li className="cat-tag-mgr-item muted">{t('sources:mgr.noCategories')}</li>
            )}
            {categories.map((c) => (
              <li key={c.id} className="cat-tag-mgr-item">
                <span>
                  {c.icon ? `${c.icon} ` : ''}
                  {c.name}
                </span>
                {typeof c.count === 'number' && c.count > 0 && (
                  <span className="muted small">×{c.count}</span>
                )}
              </li>
            ))}
          </ul>

          <span className="label" style={{ display: 'block', marginTop: 16 }}>
            {t('sources:mgr.tagsLabel', { count: tags.length })}
          </span>
          <ul className="cat-tag-mgr-list">
            {tags.length === 0 && (
              <li className="cat-tag-mgr-item muted">{t('sources:mgr.noTags')}</li>
            )}
            {tags.map((t) => (
              <li key={t.id} className="cat-tag-mgr-item">
                <span>{t.name}</span>
                {typeof t.count === 'number' && t.count > 0 && (
                  <span className="muted small">×{t.count}</span>
                )}
              </li>
            ))}
          </ul>
        </div>

        <footer className="edit-project-modal__foot">
          <button type="button" className="btn btn-primary" onClick={onClose}>
            {t('sources:mgr.done')}
          </button>
        </footer>
      </div>
    </ModalOverlay>
  );
}
