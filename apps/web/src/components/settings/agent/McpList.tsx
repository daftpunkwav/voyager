/**
 * @file McpList
 * @description List of external MCP servers with tool preview, per-item or package approval, refresh, and removal (with confirmation).
 *
 * Responsibilities:
 * - Preview each server's tools and approve per tool or the whole package
 * - Refresh tool lists and remove servers behind a confirmation dialog
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { approveMcpTools, previewMcpTools, removeMcpServer } from '@/api/agent';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { McpApproveResult, McpServerState } from './types';

interface McpListProps {
  servers: McpServerState[];
  onChange: () => void;
}

/** External MCP server list: preview, approve, refresh, remove */
export function McpList({ servers, onChange }: McpListProps) {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [checked, setChecked] = useState<Record<string, string[]>>({});
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  const refreshPreview = async (id: string) => {
    try {
      await previewMcpTools(id);
      onChange();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('mcp.list.refreshFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  const approve = async (id: string, names: string[]) => {
    try {
      const res = (await approveMcpTools(id, names)) as McpApproveResult;
      addToast({
        type: 'success',
        message: t('mcp.list.approvedToast', { count: res.mounted.length }),
      });
      onChange();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('mcp.list.approveFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  const toggleTool = (sid: string, tool: string) => {
    setChecked((prev) => {
      const cur = prev[sid] ?? [];
      return {
        ...prev,
        [sid]: cur.includes(tool) ? cur.filter((t) => t !== tool) : [...cur, tool],
      };
    });
  };

  const remove = async (id: string) => {
    try {
      await removeMcpServer(id);
      addToast({ type: 'success', message: t('mcp.list.removedToast', { id }) });
    } catch (err) {
      addToast({
        type: 'error',
        message: t('mcp.list.removeFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setConfirmRemoveId(null);
      onChange();
    }
  };

  return (
    <>
      <ul className="memory-entry-list">
        {servers.map((s) => (
          <li key={s.id} className="memory-entry">
            <span className="memory-kind">{s.name}</span>
            <span className="memory-entry-summary">
              {s.kind === 'stdio' ? `stdio · ${s.command}` : s.url}
              {' · '}
              {s.approved.includes('*')
                ? t('mcp.list.approvedAll')
                : s.approved.length > 0
                  ? t('mcp.list.approvedCount', { count: s.approved.length })
                  : t('mcp.list.notApproved')}
              {s.connected ? '' : ` · ${t('mcp.list.disconnected')}`}
            </span>
            {s.error && (
              <span className="memory-entry-summary" style={{ color: 'var(--error)' }}>
                {s.error}
              </span>
            )}
            {s.mounted.length > 0 && (
              <span className="muted" style={{ fontSize: 12 }}>
                {t('mcp.list.mounted', { count: s.mounted.length, id: s.id })}
              </span>
            )}
            {!s.approved.includes('*') && s.connected && s.preview.length > 0 && (
              <div style={{ margin: '6px 0' }}>
                {s.preview.map((t2) => (
                  <div key={t2.name} style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    {s.approval === 'item' && (
                      <input
                        type="checkbox"
                        checked={(checked[s.id] ?? []).includes(t2.name)}
                        onChange={() => toggleTool(s.id, t2.name)}
                        aria-label={`${s.id} · ${t2.name}`}
                      />
                    )}
                    <span style={{ fontSize: 12 }}>
                      <strong>{t2.name}</strong>
                      {t2.description ? ` — ${t2.description}` : ''}
                    </span>
                  </div>
                ))}
                <div className="agent-guideline-meta">
                  {s.approval === 'package' ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      aria-label={t('mcp.list.approveAllAria', { name: s.name })}
                      onClick={() => void approve(s.id, ['*'])}
                    >
                      {t('mcp.list.approveAll')}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      aria-label={t('mcp.list.approveSelectedAria', { name: s.name })}
                      disabled={(checked[s.id]?.length ?? 0) === 0}
                      onClick={() => void approve(s.id, checked[s.id] ?? [])}
                    >
                      {t('mcp.list.approveSelected')}
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="agent-guideline-meta">
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                aria-label={t('mcp.list.refreshAria', { name: s.name })}
                onClick={() => void refreshPreview(s.id)}
              >
                {t('mcp.list.refresh')}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                aria-label={t('mcp.list.removeAria', { name: s.name })}
                onClick={() => setConfirmRemoveId(s.id)}
              >
                {t('mcp.list.remove')}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {confirmRemoveId && (
        <ConfirmDialog
          open
          title={t('mcp.list.removeTitle', { id: confirmRemoveId })}
          message={t('mcp.list.removeConfirm')}
          confirmLabel={t('mcp.list.remove')}
          danger
          onConfirm={() => void remove(confirmRemoveId)}
          onCancel={() => setConfirmRemoveId(null)}
        />
      )}
    </>
  );
}
