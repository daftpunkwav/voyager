/**
 * @file LlmProviderList
 * @description Sidebar rail listing LLM providers with selection, default tag, config status, and an add button.
 *
 * Responsibilities:
 * - List providers with selection, default tag and config status
 * - Provide the add-provider entry
 */

import { useTranslation } from 'react-i18next';
import type { LlmProvider } from '@/api/types';
import { GLASS_INNER } from '@/constants/glassTokens';

interface LlmProviderListProps {
  providers: LlmProvider[];
  selectedId: string | null;
  defaultProviderId: string;
  onSelect: (id: string) => void;
  onAdd: () => void;
}

export function LlmProviderList({
  providers,
  selectedId,
  defaultProviderId,
  onSelect,
  onAdd,
}: LlmProviderListProps) {
  const { t } = useTranslation('settings');
  return (
    <aside className="llm-provider-rail glass-card glass-card--overview-inner">
      <div className="llm-provider-rail-title">{t('llm.list.title')}</div>
      <ul className="llm-provider-list">
        {providers.map((p) => {
          const active = p.id === selectedId;
          const isDefault = p.id === defaultProviderId;
          return (
            <li key={p.id}>
              <button
                type="button"
                className={`llm-provider-item ${active ? 'is-active' : ''} ${GLASS_INNER}`}
                onClick={() => onSelect(p.id)}
              >
                <span className="llm-provider-item-name">
                  {p.display_name || p.preset_id}
                  {isDefault ? (
                    <span className="llm-provider-default-tag">{t('llm.provider.defaultTag')}</span>
                  ) : null}
                </span>
                <span
                  className={`llm-provider-status ${p.enabled && p.has_api_key ? 'is-on' : ''}`}
                  title={
                    p.enabled
                      ? p.has_api_key
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
      <button
        type="button"
        className={`btn btn-sm llm-provider-add ${GLASS_INNER}`}
        onClick={onAdd}
      >
        {t('llm.list.add')}
      </button>
    </aside>
  );
}
