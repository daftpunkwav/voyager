/**
 * @file LlmProviderList
 * @description Flat provider rail for the LLM settings: selection, config
 * status dot, and the add-provider entry. Sits directly on the section panel
 * (single top-layer glass) — no nested card surface.
 *
 * Responsibilities:
 * - List providers with selection and config status
 * - Provide the add-provider entry
 */

import { useTranslation } from 'react-i18next';
import type { LlmProvider } from '@/api/types';

interface LlmProviderListProps {
  providers: LlmProvider[];
  selectedId: string | null;
  /** A placeholder provider is being created (button locked against spam). */
  creating?: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
}

export function LlmProviderList({
  providers,
  selectedId,
  creating = false,
  onSelect,
  onAdd,
}: LlmProviderListProps) {
  const { t } = useTranslation('settings');
  return (
    <aside className="llm-rail">
      <div className="llm-rail-title">
        {t('llm.list.title')}
        <span className="llm-rail-count">{providers.length}</span>
      </div>
      <ul className="llm-provider-list">
        {providers.map((p) => {
          const active = p.id === selectedId;
          const usable = p.enabled && p.has_api_key;
          return (
            <li key={p.id}>
              <button
                type="button"
                className={`llm-provider-item ${active ? 'is-active' : ''}`}
                aria-current={active ? 'true' : undefined}
                onClick={() => onSelect(p.id)}
              >
                <span className="llm-provider-item-name">{p.display_name || p.preset_id}</span>
                <span
                  className={`llm-provider-status ${usable ? 'is-on' : ''}`}
                  title={
                    p.enabled
                      ? usable
                        ? t('llm.list.keySet')
                        : t('llm.list.keyMissing')
                      : t('llm.list.disabled')
                  }
                />
              </button>
            </li>
          );
        })}
      </ul>
      <button type="button" className="llm-provider-add" disabled={creating} onClick={onAdd}>
        {t('llm.list.add')}
      </button>
    </aside>
  );
}
