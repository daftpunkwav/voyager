/**
 * @file LlmSettingsSection
 * @description Settings -> LLM client for the llm service.
 *
 * All provider operations (list/add/update/remove, API key, per-model
 * connection test) go through the thin api/llm layer. There is no
 * default-provider concept in this UI anymore: chat's composer picker keeps
 * its own selection in llm.default_provider/llm.default_model, and the host
 * adapter resolves "no explicit choice" to the first usable provider.
 *
 * Responsibilities:
 * - Load providers through the thin api/llm layer
 * - Lay out the provider rail, detail pane, add-provider dialog and delete confirm
 * - Render the Degraded state with retry when llm capabilities fail
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import {
  addProvider,
  listProviders,
  removeProvider as removeProviderApi,
  setApiKey,
  testConnection as testConnectionApi,
  updateProvider,
} from '@/api/llm';
import type { LlmProvider } from '@/api/types';
import { useUIStore } from '@/stores/uiStore';
import { LlmProviderDetail } from './llm/LlmProviderDetail';
import { LlmProviderList } from './llm/LlmProviderList';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Degraded } from '@/shell/Degraded';

/** Settings -> LLM: client for the llm service.
 *
 * Provider CRUD, keys and per-model tests ride the thin api/llm layer; the
 * backend source of truth is the llm store and platform/secrets — the key is
 * never returned and the UI only reads has_api_key.
 */
export function LlmSettingsSection() {
  const { t } = useTranslation('settings');
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<LlmProvider | null>(null);
  // Direct-create guard: rapid clicks on the rail button must not spawn
  // several placeholder providers.
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);
  const addToast = useUIStore((s) => s.addToast);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const list = await listProviders();
      setProviders(list);
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

  // Keep the selection in sync with the list: preserve the current choice when possible, otherwise fall back to the first provider
  useEffect(() => {
    if (selectedId && providers.some((p) => p.id === selectedId)) return;
    setSelectedId(providers[0]?.id ?? null);
  }, [providers, selectedId]);

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
        'display_name' | 'base_url' | 'api_format' | 'models' | 'models_meta' | 'enabled'
      >
    >
  ) => updateProvider(id, patch).then(() => reload());

  const saveKey = async (id: string, apiKey: string) => {
    await setApiKey(id, apiKey);
    await reload();
  };

  const removeProvider = async (id: string) => {
    await removeProviderApi(id);
    await reload();
  };

  /** No add dialog: one click spawns a placeholder provider and selects it;
   *  renaming, endpoint and key all happen on the detail pane. */
  const addProviderDirect = async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    setCreating(true);
    try {
      const created = await addProvider({
        display_name: t('llm.add.unnamedName'),
        base_url: 'https://api.example.com/v1',
        api_format: 'chat',
      });
      const list = await reload();
      if (created?.id) setSelectedId(created.id);
      else if (list.length) setSelectedId(list[list.length - 1].id);
    } catch (err) {
      const e = err as ServiceError;
      addToast({
        type: 'warning',
        message: e.hint ? `${e.message}(${e.hint})` : (e.message ?? t('llm.provider.actionFailed')),
      });
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  };

  return (
    <div className="llm-settings">
      {!anyUsable && (
        <div className="alert alert-warning">
          <strong>{t('llm.notConfiguredTag')}</strong> {t('llm.notConfiguredDesc')}
        </div>
      )}

      <div className="llm-layout">
        <LlmProviderList
          providers={providers}
          selectedId={selected?.id ?? null}
          creating={creating}
          onSelect={setSelectedId}
          onAdd={() => void addProviderDirect()}
        />
        <div className="llm-detail-pane" key={selected?.id ?? 'empty'}>
          {selected ? (
            <LlmProviderDetail
              provider={selected}
              onPatch={(patch) => patchProvider(selected.id, patch)}
              onSaveKey={(key) => saveKey(selected.id, key)}
              onDelete={() => setConfirmDelete(selected)}
              onTestModel={(model) => testConnectionApi(selected.id, model)}
            />
          ) : (
            <div className="llm-empty">
              {providers.length === 0 ? t('llm.emptyProviders') : t('llm.selectProviderPrompt')}
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title={t('llm.provider.deleteTitle')}
        message={t('llm.delete.confirm', { name: confirmDelete?.display_name ?? '' })}
        confirmLabel={t('llm.delete.confirmBtn')}
        danger
        onConfirm={() => {
          if (confirmDelete) void removeProvider(confirmDelete.id);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
