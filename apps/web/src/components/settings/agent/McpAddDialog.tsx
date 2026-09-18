/**
 * @file McpAddDialog
 * @description Add-external-MCP dialog (ModalOverlay): stdio command or HTTP
 * URL transport plus approval granularity. The reference "新建 MCP 服务器"
 * window; submit goes through add_mcp_server and reports the outcome via
 * toasts (connected vs saved-but-disconnected).
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { addMcpServer } from '@/api/agent';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { EMPTY_MCP_FORM } from './constants';
import type { McpAddResult, McpFormDraft } from './types';

interface McpAddDialogProps {
  open: boolean;
  onClose: () => void;
  onAdded: () => void;
}

export function McpAddDialog({ open, onClose, onAdded }: McpAddDialogProps) {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [form, setForm] = useState<McpFormDraft>(EMPTY_MCP_FORM);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setForm(EMPTY_MCP_FORM);
  }, [open]);

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
      onClose();
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
    <ModalOverlay open={open} onClose={onClose}>
      <div
        className="modal glass-card glass-card--dialog mcp-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('mcp.form.heading')}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mcp-dialog__title">{t('mcp.form.heading')}</h3>
        <div className="field-group">
          <label className="field-label" htmlFor="mcp-id">
            {t('mcp.form.idAria')}
          </label>
          <input
            id="mcp-id"
            className="field input"
            placeholder={t('mcp.form.idPlaceholder')}
            value={form.id}
            onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
            aria-label={t('mcp.form.idAria')}
          />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="mcp-name">
            {t('mcp.form.nameAria')}
          </label>
          <input
            id="mcp-name"
            className="field input"
            placeholder={t('mcp.form.namePlaceholder')}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            aria-label={t('mcp.form.nameAria')}
          />
        </div>
        <div className="mcp-dialog__grid">
          <div className="field-group">
            <span className="field-label">{t('mcp.form.kindAria')}</span>
            <GlassSelect
              value={form.kind}
              options={[
                { value: 'stdio', label: t('mcp.form.kindStdio') },
                { value: 'url', label: t('mcp.form.kindUrl') },
              ]}
              onChange={(v) => setForm((f) => ({ ...f, kind: v as McpFormDraft['kind'] }))}
              aria-label={t('mcp.form.kindAria')}
            />
          </div>
          <div className="field-group">
            <span className="field-label">{t('mcp.form.granularityAria')}</span>
            <GlassSelect
              value={form.approval}
              options={[
                { value: 'package', label: t('mcp.form.granularityPackage') },
                { value: 'item', label: t('mcp.form.granularityItem') },
              ]}
              onChange={(v) => setForm((f) => ({ ...f, approval: v as McpFormDraft['approval'] }))}
              aria-label={t('mcp.form.granularityAria')}
            />
          </div>
        </div>
        {form.kind === 'stdio' ? (
          <>
            <div className="field-group">
              <label className="field-label" htmlFor="mcp-command">
                {t('mcp.form.commandAria')}
              </label>
              <input
                id="mcp-command"
                className="field input"
                placeholder={t('mcp.form.commandPlaceholder')}
                value={form.command}
                onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                aria-label={t('mcp.form.commandAria')}
              />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="mcp-args">
                {t('mcp.form.argsAria')}
              </label>
              <textarea
                id="mcp-args"
                className="field input agent-guideline-textarea"
                rows={2}
                placeholder={t('mcp.form.argsPlaceholder')}
                value={form.argsDraft}
                onChange={(e) => setForm((f) => ({ ...f, argsDraft: e.target.value }))}
                aria-label={t('mcp.form.argsAria')}
              />
            </div>
          </>
        ) : (
          <div className="field-group">
            <label className="field-label" htmlFor="mcp-url">
              {t('mcp.form.urlAria')}
            </label>
            <input
              id="mcp-url"
              className="field input"
              placeholder={t('mcp.form.urlPlaceholder')}
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              aria-label={t('mcp.form.urlAria')}
            />
          </div>
        )}
        <div className="mcp-dialog__footer">
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            aria-label={t('mcp.form.addAria')}
            disabled={busy}
            onClick={() => void handleAdd()}
          >
            {t('mcp.form.add')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
