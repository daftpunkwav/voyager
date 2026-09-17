/**
 * @file LlmAgentOverrides
 * @description Per-agent provider/model/speaking-style override table for the
 * LLM settings, backed by two agent settings keys:
 * - agent.llm.overrides: {"<persona key>": {"provider": id, "model": name}}
 *   — consulted per turn by the host's persona-aware chat transport;
 * - agent.style.overrides: {"<persona key>": "<style text>"} — layered over
 *   the global agent.style when the system prompt is rebuilt.
 * Empty provider/model fields and an absent style entry mean "follow the
 * default"; saving drops empty entries so the stored maps stay clean.
 *
 * Responsibilities:
 * - Load both override maps once and render one row per catalog persona
 * - Persist edits straight to the settings keys (single-user local setup)
 * - Reset a provider switch when its stored model no longer exists there
 * - Surface stale stored provider/model entries instead of showing the default
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmProvider } from '@/api/types';
import { firstEnabledModel } from '@/api/llm';
import { GlassSelect } from '@/components/common/GlassSelect';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { STYLE_PRESETS } from '@/components/settings/agent/constants';

/** Settings keys (values must match the backend SettingDef registries). */
export const AGENT_LLM_OVERRIDES_KEY = 'agent.llm.overrides';
export const AGENT_STYLE_OVERRIDES_KEY = 'agent.style.overrides';

interface ModelOverride {
  provider: string;
  model: string;
}

type ModelOverrideMap = Record<string, ModelOverride>;
type StyleOverrideMap = Record<string, string>;

function normalizeMap(value: unknown): Record<string, Record<string, unknown>> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).filter(
      (entry): entry is [string, Record<string, unknown>] =>
        Boolean(entry[0]) && typeof entry[1] === 'object' && entry[1] !== null
    )
  );
}

function normalizeStyles(value: unknown): StyleOverrideMap {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out: StyleOverrideMap = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (k && typeof v === 'string' && v.trim()) out[k] = v;
  }
  return out;
}

/** Per-agent provider / model / speaking-style override table. */
export function LlmAgentOverrides({ providers }: LlmAgentOverridesProps) {
  const { t } = useTranslation('settings');
  const [modelOverrides, setModelOverrides] = useState<ModelOverrideMap>({});
  const [styleOverrides, setStyleOverrides] = useState<StyleOverrideMap>({});
  const [loaded, setLoaded] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      callCapability<{ value?: unknown }>('settings', 'get_setting', {
        key: AGENT_LLM_OVERRIDES_KEY,
      }),
      callCapability<{ value?: unknown }>('settings', 'get_setting', {
        key: AGENT_STYLE_OVERRIDES_KEY,
      }),
    ])
      .then(([llmItem, styleItem]) => {
        if (!alive) return;
        const raw = normalizeMap(llmItem?.value);
        const models: ModelOverrideMap = {};
        for (const [k, entry] of Object.entries(raw)) {
          models[k] = {
            provider: typeof entry.provider === 'string' ? entry.provider : '',
            model: typeof entry.model === 'string' ? entry.model : '',
          };
        }
        setModelOverrides(models);
        setStyleOverrides(normalizeStyles(styleItem?.value));
        setLoaded(true);
      })
      .catch(() => {
        // Unreadable keys behave like "no overrides"; edits still save over them
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const persist = async (key: string, value: unknown) => {
    setSaveError(null);
    try {
      await callCapability('settings', 'set_setting', { key, value });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  };

  // Handlers read the latest render state directly (they are recreated each
  // render), so the persist side effect stays out of the state updater —
  // StrictMode double-invokes updaters and would double-write the setting.
  const updateModelOverride = (agentId: string, patch: Partial<ModelOverride>) => {
    const current = modelOverrides[agentId] ?? { provider: '', model: '' };
    const next: ModelOverride = { ...current, ...patch };
    const map: ModelOverrideMap = { ...modelOverrides };
    if (!next.provider && !next.model) delete map[agentId];
    else map[agentId] = next;
    setModelOverrides(map);
    void persist(AGENT_LLM_OVERRIDES_KEY, map);
  };

  const updateStyleOverride = (agentId: string, style: string) => {
    const map: StyleOverrideMap = { ...styleOverrides };
    if (!style) delete map[agentId];
    else map[agentId] = style;
    setStyleOverrides(map);
    void persist(AGENT_STYLE_OVERRIDES_KEY, map);
  };

  const enabledProviders = providers.filter((p) => p.enabled);
  // No default-provider concept: an unspecified agent rides the system
  // resolution, which lands on the first usable provider.
  const fallbackProvider = enabledProviders[0];

  if (!loaded) {
    return <p className="muted small">{t('llm.loading')}</p>;
  }

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
              const override = modelOverrides[agent.id] ?? { provider: '', model: '' };
              const provider =
                enabledProviders.find((p) => p.id === override.provider) ?? fallbackProvider;
              const modelOptions = provider?.models?.length
                ? provider.models
                : ([firstEnabledModel(provider)].filter(Boolean) as string[]);
              // A stored provider that is gone or disabled would silently route
              // nowhere: keep it visible instead of masquerading as the default
              const storedProviderMissing =
                Boolean(override.provider) &&
                !enabledProviders.some((p) => p.id === override.provider);
              // A stored model that no longer exists on the selected provider
              // would silently route nowhere: surface it as the fallback entry
              const storedModelMissing =
                Boolean(override.model) && !modelOptions.includes(override.model);
              const styleValue = styleOverrides[agent.id] ?? '';

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
                      value={override.provider}
                      options={[
                        {
                          value: '',
                          label: t('llm.overrides.defaultProvider', {
                            name: fallbackProvider?.display_name ?? '—',
                          }),
                        },
                        ...enabledProviders.map((p) => ({
                          value: p.id,
                          label: p.display_name,
                        })),
                        ...(storedProviderMissing
                          ? [{ value: override.provider, label: override.provider }]
                          : []),
                      ]}
                      onChange={(v) =>
                        updateModelOverride(agent.id, {
                          provider: v,
                          // Clear the model override when switching providers so it cannot point at a nonexistent model
                          model: '',
                        })
                      }
                      aria-label={t('llm.overrides.providerAria', { name: agent.name })}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={override.model}
                      options={[
                        {
                          value: '',
                          label: t('llm.overrides.useDefaultModel', {
                            name: firstEnabledModel(provider) || '—',
                          }),
                        },
                        ...modelOptions.map((m) => ({ value: m, label: m })),
                        ...(storedModelMissing
                          ? [{ value: override.model, label: override.model }]
                          : []),
                      ]}
                      onChange={(v) => updateModelOverride(agent.id, { model: v })}
                      aria-label={t('llm.overrides.modelAria', { name: agent.name })}
                    />
                  </td>
                  <td>
                    <GlassSelect
                      size="sm"
                      value={styleValue}
                      options={[
                        { value: '', label: t('llm.overrides.styleFollowGlobal') },
                        ...STYLE_PRESETS.map((s) => ({ value: s, label: s })),
                      ]}
                      onChange={(v) => updateStyleOverride(agent.id, v)}
                      aria-label={t('llm.overrides.styleAria', { name: agent.name })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {saveError ? (
        <p className="setting-field__error small" role="alert">
          {saveError}
        </p>
      ) : null}
    </div>
  );
}

interface LlmAgentOverridesProps {
  /** Provider list from the llm service's source of truth (list_providers) */
  providers: LlmProvider[];
}
