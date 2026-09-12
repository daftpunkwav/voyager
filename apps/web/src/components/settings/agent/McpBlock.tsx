/**
 * @file McpBlock
 * @description Settings block for external MCP servers: server list plus an add form.
 *
 * Responsibilities:
 * - Load the MCP server list and refresh it after add / list actions
 * - Compose the add form and the server list halves
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listMcpServers } from '@/api/agent';
import { McpForm } from './McpForm';
import { McpList } from './McpList';
import type { McpServerState } from './types';

/** External MCP: server list + add form */
export function McpBlock() {
  const { t } = useTranslation('settings');
  const [servers, setServers] = useState<McpServerState[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const reload = () =>
    listMcpServers<McpServerState>()
      .then((items) => setServers(Array.isArray(items) ? items : []))
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

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('mcp.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('mcp.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : servers === null ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('mcp.loading')}
        </p>
      ) : servers.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('mcp.empty')}
        </p>
      ) : (
        <McpList servers={servers} onChange={reload} />
      )}
      <McpForm onAdded={reload} />
    </div>
  );
}
