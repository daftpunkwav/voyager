/**
 * @file TagEditor
 * @description Inline tag editor: chip display, Enter to add, x to remove.
 *
 * Reused by source detail pages such as DocReader / PageReader. Persistence is
 * handled by the caller via onChange (controlled component; issues no requests
 * of its own).
 *
 * Responsibilities:
 * - Render tag chips with per-chip removal
 * - Add trimmed, deduplicated tags on Enter and raise the full list via
 *   onChange
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface TagEditorProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export function TagEditor({ tags, onChange, placeholder }: TagEditorProps) {
  const { t } = useTranslation('sources');
  const [draft, setDraft] = useState('');

  const add = () => {
    const t = draft.trim();
    if (!t) return;
    if (!tags.includes(t)) onChange([...tags, t]);
    setDraft('');
  };

  const remove = (tag: string) => {
    onChange(tags.filter((x) => x !== tag));
  };

  return (
    <div className="tag-editor" role="group" aria-label={t('sources:tags.groupAria')}>
      {tags.map((tag) => (
        <span key={tag} className="tag-editor__chip">
          {tag}
          <button
            type="button"
            className="tag-editor__remove"
            aria-label={t('sources:tags.removeAria', { tag })}
            onClick={() => remove(tag)}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="tag-editor__input"
        value={draft}
        placeholder={placeholder ?? t('sources:tags.addPlaceholder')}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
    </div>
  );
}
