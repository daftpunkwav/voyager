/**
 * @file EditProjectModal
 * @description Modal for editing a project's category and tags.
 *
 * Responsibilities:
 * - Edit a project's category and tag set in a modal form
 * - Create new tags inline and persist changes via the project mutation hooks
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Category, Project, Tag } from '@/api/types';
import { useSetProjectTags, useUpdateProject } from '@/hooks/useProjects';
import { useUIStore } from '@/stores/uiStore';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface EditProjectModalProps {
  open: boolean;
  project: Project;
  categories: Category[];
  tags: Tag[];
  onClose: () => void;
}

export function EditProjectModal({
  open,
  project,
  categories,
  tags,
  onClose,
}: EditProjectModalProps) {
  const { t } = useTranslation('sources');
  // Category is a plain string field on the resource: the draft value is the category name; '' means uncategorized
  const [categoryId, setCategoryId] = useState(
    typeof project.category === 'string' ? project.category : ''
  );
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(project.tags ?? []));
  const [newTag, setNewTag] = useState('');
  const updateProject = useUpdateProject();
  const setProjectTags = useSetProjectTags();
  const addToast = useUIStore((s) => s.addToast);

  useEffect(() => {
    if (!open) return;
    setCategoryId(typeof project.category === 'string' ? project.category : '');
    setSelectedTags(new Set(project.tags ?? []));
    setNewTag('');
  }, [open, project]);

  const categoryOptions = [
    { value: '', label: t('sources:edit.uncategorized') },
    ...categories.map((c) => ({
      value: c.id,
      label: c.is_preset ? `${c.name}${t('sources:edit.presetSuffix')}` : c.name,
    })),
  ];

  const toggleTag = (id: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Tags are plain strings on the resource: a new tag goes straight into the selection set and is persisted via set_repo_meta on save
  const handleAddTag = () => {
    const name = newTag.trim();
    if (!name) return;
    setSelectedTags((prev) => new Set(prev).add(name));
    setNewTag('');
  };

  const handleSave = async () => {
    try {
      await updateProject.mutateAsync({
        id: project.id,
        data: {
          // The category is stored by name; an empty string means uncategorized (the backend list_categories excludes empty strings)
          category: categoryId,
        },
      });
      await setProjectTags.mutateAsync({
        projectId: project.id,
        tags: [...selectedTags],
      });
      addToast({ type: 'success', message: t('sources:edit.saved') });
      onClose();
    } catch {
      addToast({ type: 'error', message: t('sources:edit.saveFailed') });
    }
  };

  const pending = updateProject.isPending || setProjectTags.isPending;

  return (
    <ModalOverlay open={open} onClose={onClose}>
      <div
        className="modal modal--wide edit-project-modal glass-card glass-card--dialog glass-overflow-visible"
        role="dialog"
        aria-labelledby="edit-project-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="edit-project-modal__head">
          <div>
            <h2 id="edit-project-title">{t('sources:edit.title')}</h2>
            <p className="muted small mono">{project.name}</p>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label={t('sources:closeAria')}
          >
            ×
          </button>
        </header>

        <div className="edit-project-modal__body">
          <label className="edit-project-field">
            <span className="label">{t('sources:edit.field.category')}</span>
            <GlassSelect
              aria-label={t('sources:edit.field.categoryAria')}
              value={categoryId}
              options={categoryOptions}
              onChange={setCategoryId}
            />
          </label>

          <div className="edit-project-field">
            <span className="label">{t('sources:edit.field.tags')}</span>
            <div className="edit-project-tags">
              {tags.length === 0 && <span className="muted small">{t('sources:edit.noTags')}</span>}
              {tags.map((t) => {
                const on = selectedTags.has(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`edit-tag-chip ${on ? 'is-on' : ''}`}
                    onClick={() => toggleTag(t.id)}
                  >
                    {t.name}
                    {typeof t.count === 'number' && t.count > 0 ? (
                      <span className="edit-tag-chip__count">{t.count}</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
            <div className="edit-project-new-tag">
              <input
                className="input"
                placeholder={t('sources:edit.newTagPlaceholder')}
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void handleAddTag();
                  }
                }}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={!newTag.trim()}
                onClick={() => handleAddTag()}
              >
                {t('sources:edit.add')}
              </button>
            </div>
          </div>
        </div>

        <footer className="edit-project-modal__foot">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={pending}>
            {t('sources:cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={pending}
            onClick={() => void handleSave()}
          >
            {pending ? t('sources:edit.saving') : t('sources:edit.save')}
          </button>
        </footer>
      </div>
    </ModalOverlay>
  );
}
