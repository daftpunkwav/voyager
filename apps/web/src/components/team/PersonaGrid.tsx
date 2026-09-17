/**
 * @file PersonaGrid
 * @description Persona preset grid; loads list_personas on mount and reports its own toasts.
 *
 * Responsibilities:
 * - Load and render the persona presets with their full contract: identity
 *   (key), speaking style, default reasoning mode, the complete tool
 *   allow-list (chips, not a count) and the system prompt (collapsed)
 * - Patch the personas count into the team snapshot
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listPersonas } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { patchTeamSnapshot } from './provider';
import type { PersonaItem } from './types';

export function PersonaGrid() {
  const { t } = useTranslation('team');
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const arr = await listPersonas<PersonaItem>();
      setPersonas(arr);
      patchTeamSnapshot({ personas: arr.length });
    } catch (err) {
      setError(extractErrorMessage(err));
      addToast({
        type: 'error',
        message: t('team:persona.loadFailedToast', { message: extractErrorMessage(err) }),
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetch on mount only; load closes over latest state, so adding it to deps would refetch every render
  }, []);

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:persona.title')}</h2>
        <LoadingSpinner label={t('team:persona.loading')} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:persona.title')}</h2>
        <EmptyState
          title={t('team:persona.loadFailed')}
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">{t('team:persona.title')}</h2>
      <div className="team-grid">
        {personas.length === 0 ? (
          <EmptyState
            title={t('team:persona.empty.title')}
            description={t('team:persona.empty.description')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          personas.map((p) => (
            <article key={p.key} className="persona-card">
              <div className="persona-card__head">
                <h3 className="h3">{p.display_name}</h3>
                <span className="chip brand">{p.key}</span>
              </div>

              <dl className="persona-card__facts">
                <div className="persona-fact">
                  <dt>{t('team:persona.styleLabel')}</dt>
                  <dd>{p.style}</dd>
                </div>
                <div className="persona-fact">
                  <dt>{t('team:persona.modeLabel')}</dt>
                  <dd>{p.default_mode}</dd>
                </div>
                <div className="persona-fact">
                  <dt>{t('team:persona.toolsLabel')}</dt>
                  <dd>
                    {p.tool_allow?.length
                      ? t('team:tools.count', { n: p.tool_allow.length })
                      : t('team:tools.unrestricted')}
                  </dd>
                </div>
              </dl>

              {p.tool_allow?.length ? (
                <details className="persona-card__details">
                  <summary>{t('team:tools.list')}</summary>
                  <div className="persona-tool-list">
                    {p.tool_allow.map((tool) => (
                      <span key={tool} className="persona-tool-chip">
                        {tool}
                      </span>
                    ))}
                  </div>
                </details>
              ) : null}

              <details className="persona-card__details">
                <summary>{t('team:persona.systemPrompt')}</summary>
                <pre className="system-prompt">{p.system_prompt}</pre>
              </details>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
