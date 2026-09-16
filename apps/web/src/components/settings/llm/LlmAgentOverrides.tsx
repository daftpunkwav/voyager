/**
 * @file LlmAgentOverrides
 * @description Per-agent provider/model/speaking-style override table for the LLM settings.
 *
 * KNOWN GAP: the backend has no storage for per-agent overrides yet (no
 * agent_llm_configs key or equivalent capability), so the table is
 * presentation-local: edits update this component's state and toast an
 * explicit "not persisted" warning instead of silently failing against a
 * fictional settings-blob contract. Wiring a real backend key is future work.
 *
 * Responsibilities:
 * - Render the per-agent provider / model / speaking-style override table as a
 *   flat inner block (single top-layer glass principle: the section panel is
 *   the only glass surface; titles live at section level)
 * - Keep edits presentation-local and toast the explicit not-persisted warning
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AgentLlmConfig, AgentSpeakingStyle, LlmProvider } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { SPEAKING_STYLE_OPTIONS } from '@/constants/llmConfig';
import { useUIStore } from '@/stores/uiStore';

interface LlmAgentOverridesProps {
  /** Provider list from the llm service's source of truth (list_providers) */
  providers: LlmProvider[];
  /** Current value of the llm.default_provider setting */
  defaultProviderId: string;
}

function defaultConfig(agentId: string): AgentLlmConfig {
  return {
    agent_id: agentId,
    provider_id: null,
    model_override: null,
    speaking_style: 'default' as AgentSpeakingStyle,
  };
}

/** Per-agent provider and style override table: the provider dropdowns draw from the llm.* source of truth;
 *  per-agent overrides are presentation-local until a backend contract exists. */
export function LlmAgentOverrides({ providers, defaultProviderId }: LlmAgentOverridesProps) {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [configs, setConfigs] = useState<AgentLlmConfig[]>(() =>
    AGENT_CATALOG.map((a) => defaultConfig(a.id))
  );

  const agentConfigsMap = useMemo(() => new Map(configs.map((c) => [c.agent_id, c])), [configs]);

  const enabledProviders = providers.filter((p) => p.enabled);
  const defaultProvider = providers.find((p) => p.id === defaultProviderId) ?? enabledProviders[0];

  const updateAgentConfig = (agentId: string, patch: Partial<AgentLlmConfig>) => {
    setConfigs((prev) => prev.map((c) => (c.agent_id === agentId ? { ...c, ...patch } : c)));
    addToast({ type: 'warning', message: t('toast.agentOverridesNotPersisted') });
  };

  return (
    <div className="llm-settings-block">
      <div className="llm-agent-table-wrap">
        <table className="llm-agent-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>{t('llm.overrides.provider')}</th>
              <th>{t('llm.overrides.model')}</th>
              <th>{t('llm.overrides.style')}</th>
            </tr>
          </thead>
          <tbody>
            {AGENT_CATALOG.map((agent) => {
              const cfg = agentConfigsMap.get(agent.id) ?? {
                agent_id: agent.id,
                provider_id: null,
                model_override: null,
                speaking_style: 'default' as AgentSpeakingStyle,
              };
              const provider =
                enabledProviders.find((p) => p.id === cfg.provider_id) ?? defaultProvider;
              const modelOptions = provider?.models?.length
                ? provider.models
                : ([provider?.default_model].filter(Boolean) as string[]);

              return (
                <tr key={agent.id}>
                  <td>
                    <div className="llm-agent-cell">
                      <span
                        className="llm-agent-avatar"
                        style={{ background: agent.color }}
                        aria-hidden
                      >
                        {agent.name[0]}
                      </span>
                      <div>
                        <div className="llm-agent-name">{agent.name}</div>
                        <div className="llm-agent-tagline muted">{agent.tagline}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.provider_id ?? ''}
                      options={[
                        {
                          value: '',
                          label: t('llm.overrides.defaultProvider', {
                            name: defaultProvider?.display_name ?? '—',
                          }),
                        },
                        ...enabledProviders.map((p) => ({
                          value: p.id,
                          label: p.display_name,
                        })),
                      ]}
                      onChange={(v) =>
                        updateAgentConfig(agent.id, {
                          provider_id: v || null,
                          // Clear the model override when switching providers so it cannot point at a nonexistent model
                          model_override: null,
                        })
                      }
                      aria-label={t('llm.overrides.providerAria', { name: agent.name })}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.model_override ?? ''}
                      options={[
                        {
                          value: '',
                          label: t('llm.overrides.useDefaultModel', {
                            name: provider?.default_model || '—',
                          }),
                        },
                        ...modelOptions.map((m) => ({ value: m, label: m })),
                      ]}
                      onChange={(v) => updateAgentConfig(agent.id, { model_override: v || null })}
                      aria-label={t('llm.overrides.modelAria', { name: agent.name })}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={cfg.speaking_style}
                      options={SPEAKING_STYLE_OPTIONS.map((opt) => ({
                        value: opt.value,
                        label: `${t(opt.labelKey)} — ${t(opt.descKey)}`,
                      }))}
                      onChange={(v) =>
                        updateAgentConfig(agent.id, {
                          speaking_style: v as AgentSpeakingStyle,
                        })
                      }
                      aria-label={t('llm.overrides.styleAria', { name: agent.name })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
