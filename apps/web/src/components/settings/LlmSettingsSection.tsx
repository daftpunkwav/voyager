/**
 * @file LlmSettingsSection
 * @description Settings -> LLM client for the llm service.
 *
 * llm.* capabilities (list/add/update/remove, API key, connection test) go through
 * the thin api/llm layer; settings.set_setting (llm.default_provider) is the one
 * established exception and is called directly. The legacy settings blob's
 * llm_providers is no longer read or written — the source of truth is the llm store
 * and platform/secrets; keys are never returned, the UI only sees has_api_key.
 *
 * Responsibilities:
 * - Load providers and the default provider id through the thin api/llm layer
 * - Lay out the provider rail, add form, detail card and per-agent overrides
 * - Render the Degraded state with retry when llm capabilities fail
 */

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { callCapability, ServiceError } from '@/bridge/client';
import {
  listProviders,
  removeProvider as removeProviderApi,
  setApiKey,
  testConnection as testConnectionApi,
  updateProvider,
} from '@/api/llm';
import type { LlmProvider, LlmTestOutcome } from '@/api/types';
import { LLM_PROVIDER_KEY } from '@/api/settings';
import { LlmProviderAdd } from './llm/LlmProviderAdd';
import { LlmProviderDetail } from './llm/LlmProviderDetail';
import { LlmProviderList } from './llm/LlmProviderList';
import { Degraded } from '@/shell/Degraded';

/** Settings -> LLM: client for the llm service.
 *
 * llm.* capabilities (list/add/update/remove, key, connection test) go through the
 * thin api/llm layer; settings.set_setting (llm.default_provider) is an established
 * exception called directly. The legacy settings blob's llm_providers is no longer
 * read or written — the backend source of truth is the llm store and platform/secrets;
 * the key is never returned and the UI only reads has_api_key.
 */
export function LlmSettingsSection() {
  const { t } = useTranslation('settings');
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [defaultId, setDefaultId] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmTestOutcome | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [list, defItem] = await Promise.all([
        listProviders(),
        callCapability<{ value?: unknown }>('settings', 'get_setting', {
          key: LLM_PROVIDER_KEY,
        }),
      ]);
      setProviders(list);
      setDefaultId(String(defItem?.value ?? ''));
      setLoading(false);
      return list;
    } catch (err) {
      const e = err as ServiceError;
      setError({ code: e.code, message: e.message });
      setLoading(false);
      return [];
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Keep the selection in sync with the list: preserve the current choice when possible, otherwise fall back to default/first
  useEffect(() => {
    if (selectedId && providers.some((p) => p.id === selectedId)) return;
    setSelectedId(providers.find((p) => p.id === defaultId)?.id ?? providers[0]?.id ?? null);
  }, [providers, defaultId, selectedId]);

  if (loading) {
    return <p className="muted small">{t('llm.loading')}</p>;
  }
  if (error) {
    return <Degraded code={error.code} message={error.message} onRetry={() => void reload()} />;
  }

  const selected = providers.find((p) => p.id === selectedId) ?? null;
  const anyUsable = providers.some((p) => p.enabled && p.has_api_key);

  /** Metadata patch: update_provider (no key; format enum: chat / anthropic / responses) */
  const patchProvider = (
    id: string,
    patch: Partial<
      Pick<
        LlmProvider,
        | 'display_name'
        | 'base_url'
        | 'api_format'
        | 'models'
        | 'models_meta'
        | 'default_model'
        | 'enabled'
      >
    >
  ) => updateProvider(id, patch).then(() => reload());

  const saveKey = async (id: string, apiKey: string) => {
    await setApiKey(id, apiKey);
    await reload();
  };

  const testConnection = async (id: string, model: string) => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const out = await testConnectionApi(id, model);
      setTestResult(out);
    } catch (err) {
      // Capability-layer errors (e.g. missing key) surface the backend error as-is instead of fabricating success/reply fields
      const e = err as ServiceError;
      setTestResult({ ok: false, error: e.hint ? `${e.message}(${e.hint})` : e.message });
    } finally {
      setIsTesting(false);
    }
  };

  const removeProvider = async (id: string) => {
    await removeProviderApi(id);
    // When removing the default provider, clear the setting so ServiceLLM does not resolve to a deleted id (it would fall back automatically, but the setting should stay honest)
    if (defaultId === id) {
      await callCapability('settings', 'set_setting', {
        key: LLM_PROVIDER_KEY,
        value: '',
      });
      setDefaultId('');
    }
    await reload();
  };

  const setDefault = async (id: string) => {
    await callCapability('settings', 'set_setting', {
      key: LLM_PROVIDER_KEY,
      value: id,
    });
    setDefaultId(id);
  };

  return (
    <div className="llm-settings">
      {!anyUsable && (
        <div className="alert alert-warning">
          <strong>{t('llm.notConfiguredTag')}</strong> {t('llm.notConfiguredDesc')}
        </div>
      )}

      <p className="section-desc" style={{ marginTop: 0 }}>
        {t('llm.multiProviderHint')}
        <Link to="/usage" style={{ marginLeft: 8 }}>
          {t('llm.viewUsage')}
        </Link>
      </p>

      <div className="llm-multi-layout">
        <LlmProviderList
          providers={providers}
          selectedId={selected?.id ?? null}
          defaultProviderId={defaultId}
          onSelect={setSelectedId}
          onAdd={() => setAdding((v) => !v)}
        />
        <div>
          {adding ? (
            <LlmProviderAdd
              onDone={async (id) => {
                setAdding(false);
                await reload();
                if (id) setSelectedId(id);
              }}
            />
          ) : null}
          {selected ? (
            <LlmProviderDetail
              provider={selected}
              isDefault={selected.id === defaultId}
              isTesting={isTesting}
              testResult={testResult}
              onPatch={(patch) => patchProvider(selected.id, patch)}
              onSaveKey={(key) => saveKey(selected.id, key)}
              onSetDefault={() => void setDefault(selected.id)}
              onDelete={() => void removeProvider(selected.id)}
              onTest={(model) => void testConnection(selected.id, model)}
            />
          ) : (
            <div className="glass-card glass-card--overview-inner" style={{ padding: 24 }}>
              {providers.length === 0 ? t('llm.emptyProviders') : t('llm.selectProviderPrompt')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
