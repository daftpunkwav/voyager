/**
 * @file McpForm
 * @description Add form for external MCP servers (stdio command or HTTP URL) with approval granularity selection.
 *
 * Responsibilities:
 * - Collect server id, transport (stdio command or HTTP URL) and approval granularity
 * - Add the server through the agent api and toast the outcome
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { addMcpServer } from '@/api/agent';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { EMPTY_MCP_FORM } from './constants';
import type { McpAddResult, McpFormDraft } from './types';

interface McpFormProps {
  onAdded: () => void;
}

/** Add form for external MCP servers */
export function McpForm({ onAdded }: McpFormProps) {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [form, setForm] = useState<McpFormDraft>(EMPTY_MCP_FORM);
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    const id = form.id.trim();
    if (!/^[a-z][a-z0-9-]{0,31}$/.test(id)) {
      addToast({ type: 'warning', message: t('mcp.form.invalidId') });
      return;
    }
    setBusy(true);
    try {
      const res = (await addMcpServer({
        id,
        name: form.name.trim() || id,
        kind: form.kind,
        command: form.kind === 'stdio' ? form.command.trim() : '',
        args:
          form.kind === 'stdio'
            ? form.argsDraft
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean)
            : [],
        url: form.kind === 'url' ? form.url.trim() : '',
        approval: form.approval,
      })) as McpAddResult;
      setForm(EMPTY_MCP_FORM);
      if (res.connected) {
        addToast({
          type: 'success',
          message: t('mcp.form.addedConnected', { id }),
        });
      } else {
        addToast({
          type: 'warning',
          message: t('mcp.form.addedDisconnected', { id, error: res.error }),
        });
      }
      onAdded();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('mcp.form.addFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="memory-subhead">{t('mcp.form.heading')}</div>
      <div className="memory-form-row">
        <input
          className="field input"
          style={{ maxWidth: 160 }}
          placeholder={t('mcp.form.idPlaceholder')}
          value={form.id}
          onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
          aria-label={t('mcp.form.idAria')}
        />
        <input
          className="field input"
          style={{ maxWidth: 160 }}
          placeholder={t('mcp.form.namePlaceholder')}
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          aria-label={t('mcp.form.nameAria')}
        />
        <GlassSelect
          size="sm"
          value={form.kind}
          options={[
            { value: 'stdio', label: t('mcp.form.kindStdio') },
            { value: 'url', label: t('mcp.form.kindUrl') },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, kind: v as McpFormDraft['kind'] }))}
          aria-label={t('mcp.form.kindAria')}
        />
        <GlassSelect
          size="sm"
          value={form.approval}
          options={[
            { value: 'package', label: t('mcp.form.granularityPackage') },
            { value: 'item', label: t('mcp.form.granularityItem') },
          ]}
          onChange={(v) => setForm((f) => ({ ...f, approval: v as McpFormDraft['approval'] }))}
          aria-label={t('mcp.form.granularityAria')}
        />
      </div>
      {form.kind === 'stdio' ? (
        <>
          <div className="memory-form-row">
            <input
              className="field input"
              placeholder={t('mcp.form.commandPlaceholder')}
              value={form.command}
              onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
              aria-label={t('mcp.form.commandAria')}
            />
          </div>
          <textarea
            className="field input agent-guideline-textarea"
            rows={2}
            placeholder={t('mcp.form.argsPlaceholder')}
            value={form.argsDraft}
            onChange={(e) => setForm((f) => ({ ...f, argsDraft: e.target.value }))}
            aria-label={t('mcp.form.argsAria')}
          />
        </>
      ) : (
        <div className="memory-form-row">
          <input
            className="field input"
            placeholder={t('mcp.form.urlPlaceholder')}
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            aria-label={t('mcp.form.urlAria')}
          />
        </div>
      )}
      <div className="agent-guideline-meta">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          aria-label={t('mcp.form.addAria')}
          disabled={busy}
          onClick={() => void handleAdd()}
        >
          {t('mcp.form.add')}
        </button>
      </div>
    </>
  );
}
