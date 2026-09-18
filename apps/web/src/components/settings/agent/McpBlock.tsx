/**
 * @file McpBlock
 * @description Settings block for external MCP servers, in the reference
 * settings layout: toolbar (count + search + refresh + 新建) above a row list;
 * each row shows transport/endpoint, connection state and approval status and
 * expands to the tool preview / approval controls. Adding happens in the
 * McpAddDialog.
 *
 * Responsibilities:
 * - Load the MCP server list and refresh it after add / preview / approve /
 *   remove actions
 * - Expand a row to preview its tools and approve per item or the whole
 *   package
 * - Remove servers behind a confirmation dialog
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { approveMcpTools, listMcpServers, previewMcpTools, removeMcpServer } from '@/api/agent';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { McpAddDialog } from './McpAddDialog';
import type { McpApproveResult, McpServerState } from './types';

function idHue(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) % 360;
  return hash;
}

export function McpBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [servers, setServers] = useState<McpServerState[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [search, setSearch] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, string[]>>({});
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  const reload = () =>
    listMcpServers<McpServerState>()
      .then((items) => {
        setServers(Array.isArray(items) ? items : []);
        setLoadFailed(false);
      })
      .catch(() => undefined); // Post-action refresh failure: keep the current list silently; toasts are the caller's job

  useEffect(() => {
    let alive = true;
    listMcpServers<McpServerState>()
      .then((items) => {
        if (alive) setServers(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return servers ?? [];
    return (servers ?? []).filter(
      (s) => s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
    );
  }, [servers, search]);

  const onChange = () => void reload();

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
        [sid]: cur.includes(tool) ? cur.filter((x) => x !== tool) : [...cur, tool],
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

  if (loadFailed) {
    return (
      <EmptyState
        title={t('mcp.loadFailedTitle')}
        description={t('common.loadFailed')}
        icon={EmptyStateIcons.warning}
        onRetry={() => void reload()}
      />
    );
  }
  if (servers === null) {
    return <LoadingSpinner label={t('mcp.loading')} />;
  }

  return (
    <div className="mcp-block">
      <SettingsToolbar
        countLabel={t('mcp.installed')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('mcp.searchPlaceholder')}
        actions={
          <>
            <button
              type="button"
              className="llm-icon-btn"
              aria-label={t('mcp.list.refreshAllAria')}
              onClick={() => void reload()}
            >
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                <path d="M21 3v6h-6" />
              </svg>
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setAddOpen(true)}
            >
              + {t('mcp.form.create')}
            </button>
          </>
        }
      />

      {filtered.length === 0 ? (
        servers.length === 0 ? (
          <EmptyState
            title={t('mcp.emptyTitle')}
            description={t('mcp.empty')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <p className="muted small">{t('mcp.searchEmpty')}</p>
        )
      ) : (
        <ul className="settings-rows">
          {filtered.map((s) => {
            const open = expandedId === s.id;
            return (
              <li key={s.id} className="settings-row entity-row mcp-row">
                <span className="entity-icon" style={{ '--h': idHue(s.id) } as CSSProperties}>
                  {s.name.slice(0, 1).toUpperCase()}
                </span>
                <button
                  type="button"
                  className="entity-row__main entity-row__open"
                  aria-expanded={open}
                  onClick={() => setExpandedId(open ? null : s.id)}
                >
                  <span className="entity-row__title">
                    <span className="entity-row__name mono">{s.name}</span>
                    <span className={`mcp-row__dot${s.connected ? ' is-ok' : ' is-bad'}`} />
                    <span className="chip">
                      {s.kind === 'stdio' ? t('mcp.form.kindStdio') : t('mcp.form.kindUrl')}
                    </span>
                    <span className="chip">
                      {s.approved.includes('*')
                        ? t('mcp.list.approvedAll')
                        : s.approved.length > 0
                          ? t('mcp.list.approvedCount', { count: s.approved.length })
                          : t('mcp.list.notApproved')}
                    </span>
                    {!s.connected && <span className="chip">{t('mcp.list.disconnected')}</span>}
                    {s.mounted.length > 0 && (
                      <span className="entity-row__meta">
                        {t('mcp.list.mounted', { count: s.mounted.length, id: s.id })}
                      </span>
                    )}
                  </span>
                  <span className="entity-row__desc mono">
                    {s.kind === 'stdio' ? `stdio · ${s.command}` : s.url}
                  </span>
                  {s.error && <span className="mcp-row__error">{s.error}</span>}
                </button>
                <div className="entity-row__actions">
                  <button
                    type="button"
                    className="llm-icon-btn"
                    aria-label={t('mcp.list.refreshAria', { name: s.name })}
                    onClick={() => void refreshPreview(s.id)}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      width="15"
                      height="15"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                      <path d="M21 3v6h-6" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="llm-icon-btn is-danger"
                    aria-label={t('mcp.list.removeAria', { name: s.name })}
                    onClick={() => setConfirmRemoveId(s.id)}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      width="15"
                      height="15"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <path d="M3 6h18" />
                      <path d="M8 6V4h8v2" />
                      <path d="M6 6l1 14h10l1-14" />
                    </svg>
                  </button>
                </div>
                {open && (
                  <div className="mcp-row__tools">
                    {s.approved.includes('*') || s.preview.length === 0 ? (
                      <p className="muted small">
                        {s.approved.includes('*')
                          ? t('mcp.list.approvedAllHint')
                          : t('mcp.list.noPreview')}
                      </p>
                    ) : (
                      <>
                        {s.preview.map((tool) => (
                          <label key={tool.name} className="mcp-row__tool">
                            {s.approval === 'item' && (
                              <input
                                type="checkbox"
                                checked={(checked[s.id] ?? []).includes(tool.name)}
                                onChange={() => toggleTool(s.id, tool.name)}
                                aria-label={`${s.id} · ${tool.name}`}
                              />
                            )}
                            <span>
                              <strong className="mono">{tool.name}</strong>
                              {tool.description ? ` — ${tool.description}` : ''}
                            </span>
                          </label>
                        ))}
                        <div className="mcp-row__tool-actions">
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
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <McpAddDialog open={addOpen} onClose={() => setAddOpen(false)} onAdded={onChange} />

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
    </div>
  );
}
