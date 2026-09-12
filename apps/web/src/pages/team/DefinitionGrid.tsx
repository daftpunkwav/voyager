/**
 * @file DefinitionGrid
 * @description Grid of custom subagent definitions; loads list_subagents.definitions and refreshes via defsEvents.
 *
 * Responsibilities:
 * - Load custom definitions plus personas and render the definition cards
 *   (mode/network labels via the shared resolvers)
 * - Refresh silently on spawn notifications from defsEvents
 * - Patch the personas/definitions counts into the team snapshot
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listPersonas, listSubagents } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { onTeamDefsChanged } from './defsEvents';
import { patchTeamSnapshot } from './provider';
import { modeLabel, networkLabel } from './constants';
import type { PersonaItem, SubagentDef } from './types';

export function DefinitionGrid() {
  const { t } = useTranslation('team');
  const [definitions, setDefinitions] = useState<SubagentDef[]>([]);
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  /** silent: refresh after a successful spawn skips the loading spinner so cards do not flicker (keeps unit/visual tests stable). */
  const load = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const [s, personasArr] = await Promise.all([listSubagents(), listPersonas<PersonaItem>()]);
      const defsArr = (s.definitions as SubagentDef[]) ?? [];
      setDefinitions(defsArr);
      setPersonas(personasArr);
      patchTeamSnapshot({ definitions: defsArr.length });
    } catch (err) {
      if (!silent) setError(extractErrorMessage(err));
      addToast({
        type: 'error',
        message: t('team:def.loadFailedToast', { message: extractErrorMessage(err) }),
      });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    return onTeamDefsChanged(() => {
      void load({ silent: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetch on mount + subscribe to team changes; load closes over latest state, so adding it to deps would resubscribe every render
  }, []);

  const personaName = (key: string) => {
    if (!key) return t('team:persona.unbound');
    return personas.find((p) => p.key === key)?.display_name ?? key;
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:def.title')}</h2>
        <LoadingSpinner label={t('team:def.loading')} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:def.title')}</h2>
        <EmptyState
          title={t('team:def.loadFailed')}
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">{t('team:def.title')}</h2>
      <div className="team-grid">
        {definitions.length === 0 ? (
          <EmptyState
            title={t('team:def.empty.title')}
            description={t('team:def.empty.description')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          definitions.map((d) => (
            <GlassCard key={d.name} className="persona-card">
              <div className="persona-card__head">
                <h3 className="h3">{d.name}</h3>
                <span className="chip brand">{modeLabel(t, d.mode)}</span>
              </div>
              <p className="muted small">{d.description}</p>
              <p className="small">{t('team:label.persona', { name: personaName(d.persona) })}</p>
              <p className="small">
                {t('team:label.tools', {
                  value: d.allowed_tools
                    ? t('team:tools.count', { n: d.allowed_tools.length })
                    : t('team:tools.unrestricted'),
                })}
              </p>
              <p className="small">
                {t('team:label.rounds', {
                  value:
                    d.max_rounds == null && d.max_tool_calls == null
                      ? t('team:option.followGlobal')
                      : `${d.max_rounds ?? t('team:option.global')} / ${d.max_tool_calls ?? t('team:option.global')}`,
                })}
              </p>
              <p className="small">
                {t('team:label.network', { value: networkLabel(t, d.network_mode ?? '') })}
              </p>
              {d.allowed_tools && d.allowed_tools.length > 0 && (
                <details className="small">
                  <summary>{t('team:tools.list')}</summary>
                  <pre className="system-prompt">{d.allowed_tools.join('\n')}</pre>
                </details>
              )}
            </GlassCard>
          ))
        )}
      </div>
    </section>
  );
}
