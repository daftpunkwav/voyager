/**
 * @file ToolCatalog
 * @description Tool catalog section; loads list_tools on mount and lists each tool's name and description.
 *
 * Responsibilities:
 * - Load and render the tool catalog (name plus description per tool)
 * - Report load failures as toasts with the extracted message
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listTools } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import type { ToolItem } from './types';

export function ToolCatalog() {
  const { t } = useTranslation('team');
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setTools(await listTools<ToolItem>());
    } catch (err) {
      setError(extractErrorMessage(err));
      addToast({
        type: 'error',
        message: t('team:tool.loadFailedToast', { message: extractErrorMessage(err) }),
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
        <h2 className="h3">{t('team:tool.title')}</h2>
        <LoadingSpinner label={t('team:tool.loading')} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:tool.title')}</h2>
        <EmptyState
          title={t('team:tool.loadFailed')}
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">{t('team:tool.title')}</h2>
      <GlassCard>
        {tools.length === 0 ? (
          <EmptyState
            title={t('team:tool.empty.title')}
            description={t('team:tool.empty.description')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <ul className="tool-list">
            {tools.map((t) => (
              <li key={t.name} className="tool-list__item">
                <code className="mono">{t.name}</code>
                <span className="muted small">{t.description}</span>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>
    </section>
  );
}
