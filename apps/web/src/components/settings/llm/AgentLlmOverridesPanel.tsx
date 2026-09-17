/**
 * @file AgentLlmOverridesPanel
 * @description Settings -> agent-capabilities "Agent providers & style" tab:
 * loads the provider list and renders the per-agent override table (same
 * llm.* source of truth as the LLM tab).
 *
 * Responsibilities:
 * - Own the provider loading and degraded state for the overrides table
 * - Render LlmAgentOverrides once the provider data is ready
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import { listProviders } from '@/api/llm';
import type { LlmProvider } from '@/api/types';
import { LlmAgentOverrides } from './LlmAgentOverrides';
import { Degraded } from '@/shell/Degraded';

export function AgentLlmOverridesPanel() {
  const { t } = useTranslation('settings');
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setProviders(await listProviders());
      setLoading(false);
    } catch (err) {
      const e = err as ServiceError;
      setError({ code: e.code, message: e.message });
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (loading) {
    return <p className="muted small">{t('llm.loading')}</p>;
  }
  if (error) {
    return <Degraded code={error.code} message={error.message} onRetry={() => void reload()} />;
  }

  return <LlmAgentOverrides providers={providers} />;
}
