/**
 * @file PluginsBlock
 * @description Settings block for declarative plugins in the reference layout:
 * toolbar (count + search + 安装) above a row list; each row carries the
 * approval state as a switch (approve-bundle on, revoke off), a delete action
 * for unapproved plugins, and an expandable per-item approval picker. The
 * install wizard (zip upload / local directory / overwrite) lives in a modal.
 *
 * Approval mounts a plugin's skills and hooks immediately; bundled MCP configs
 * are only registered as pending entries. Unapproving also reclaims the
 * plugin's registered external MCP servers that have no approved tools.
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { uploadFile } from '@/bridge/client';
import { installPlugin, listPlugins, setPluginApproval, uninstallPlugin } from '@/api/agent';
import { i18n } from '@/i18n';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import { Switch } from '@/components/common/Switch';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { PluginApproveResult, PluginInstallResult, PluginItem } from './types';

/** Semantic approval verbs; display copy resolves through settings:plugins.verb.* */
type ApprovalVerb = 'approve' | 'revoke';

function nameHue(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) % 360;
  return hash;
}

/** Permission summary: lists scopes one by one; network/fs tiers shown only when non-empty (emphasized in the pre-approval list) */
function permissionSummary(p: PluginItem): string {
  const parts: string[] = [];
  if (p.permissions.scopes.length > 0) parts.push(p.permissions.scopes.join('、'));
  if (p.permissions.network)
    parts.push(i18n.t('settings:plugins.permNetwork', { value: p.permissions.network }));
  if (p.permissions.fs) parts.push(i18n.t('settings:plugins.permFs', { value: p.permissions.fs }));
  return parts.length > 0 ? parts.join(' · ') : i18n.t('settings:plugins.permNone');
}

function resultMessage(verb: ApprovalVerb, res: PluginApproveResult): string {
  // Revoking or changing picks reclaims the plugin's registered external MCP servers per the safety rules; the response discloses the outcome
  const reclaimed = res.mcp_reclaimed ?? [];
  const reclaimSkipped = res.mcp_reclaim_skipped ?? [];
  if (verb === 'revoke') {
    let msg = i18n.t('settings:plugins.revoked', { name: res.name });
    if (reclaimed.length > 0)
      msg += i18n.t('settings:plugins.revokedMcpReclaimed', { list: reclaimed.join('、') });
    if (reclaimSkipped.length > 0) {
      const detail = reclaimSkipped.map((s) => `${s.id}（${s.reason}）`).join('、');
      msg += i18n.t('settings:plugins.revokedMcpSkipped', { detail });
    }
    return msg;
  }
  const loaded = res.loaded;
  const skipped = res.skipped;
  let msg = i18n.t('settings:plugins.approved', {
    name: res.name,
    skills: loaded.skills.length,
    hooks: loaded.hooks,
  });
  if (loaded.mcp_registered > 0) {
    msg += i18n.t('settings:plugins.mcpRegistered', { count: loaded.mcp_registered });
  }
  if (reclaimed.length > 0)
    msg += i18n.t('settings:plugins.mcpReclaimed', { list: reclaimed.join('、') });
  if (skipped) {
    const n = skipped.skills.length + skipped.hooks.length + skipped.mcp.length;
    if (n > 0) msg += i18n.t('settings:plugins.skippedItems', { count: n });
  }
  return msg;
}

export interface PluginPicks {
  skills: string[];
  hooks: string[];
  mcp: string[];
}

/** Per-item picker: unapproved plugins show their permission list + contains details; submit as a custom approval */
function PluginPicker({
  p,
  busy,
  onCancel,
  onSubmit,
}: {
  p: PluginItem;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (picks: PluginPicks) => void;
}) {
  const { t } = useTranslation('settings');
  const [picks, setPicks] = useState<PluginPicks>(() => ({
    skills: p.approved ? p.skills.filter((s) => s.approved).map((s) => s.name) : [],
    hooks: p.approved ? p.hooks.filter((h) => h.approved).map((h) => h.path) : [],
    mcp: p.approved ? p.mcp.filter((m) => m.approved).map((m) => m.id) : [],
  }));
  const anyPicked = picks.skills.length + picks.hooks.length + picks.mcp.length > 0;

  const toggle = (kind: keyof PluginPicks, value: string) => {
    setPicks((prev) => {
      const list = prev[kind];
      const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
      return { ...prev, [kind]: next };
    });
  };

  return (
    <div className="plugin-picker">
      {!p.approved && (
        <p className="muted" style={{ fontSize: 12, margin: '6px 0' }}>
          {t('plugins.requestPermission')}
          <strong>{permissionSummary(p)}</strong>
        </p>
      )}
      {p.skills.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">{t('plugins.skills')}</div>
          {p.skills.map((s) => (
            <label key={s.name} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.skills.includes(s.name)}
                onChange={() => toggle('skills', s.name)}
              />
              {s.name}
            </label>
          ))}
        </div>
      )}
      {p.hooks.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">{t('plugins.hooks')}</div>
          {p.hooks.map((h) => (
            <label key={h.path} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.hooks.includes(h.path)}
                onChange={() => toggle('hooks', h.path)}
              />
              {h.on}
              {h.enabled ? '' : t('plugins.defaultDisabled')}
            </label>
          ))}
        </div>
      )}
      {p.mcp.length > 0 && (
        <div className="plugin-picker-group">
          <div className="plugin-picker-label">MCP server</div>
          {p.mcp.map((m) => (
            <label key={m.id} className="plugin-picker-option">
              <input
                type="checkbox"
                checked={picks.mcp.includes(m.id)}
                onChange={() => toggle('mcp', m.id)}
              />
              {m.id}
              {m.registered ? t('plugins.registeredPending') : ''}
            </label>
          ))}
        </div>
      )}
      {p.mcp.length > 0 && (
        <p className="muted" style={{ fontSize: 11, margin: '4px 0 0' }}>
          {t('plugins.mcpNote')}
        </p>
      )}
      <div className="plugin-picker-actions">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={busy || !anyPicked}
          onClick={() => onSubmit(picks)}
        >
          {t('plugins.approveCustom')}
        </button>
        <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
      {!anyPicked && (
        <p className="muted" style={{ fontSize: 11, margin: '4px 0 0' }}>
          {t('plugins.pickRequired')}
        </p>
      )}
    </div>
  );
}

/** Install wizard dialog: zip upload or local directory path, with overwrite confirmation. */
function PluginInstallDialog({
  open,
  busy,
  onClose,
  onInstall,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onInstall: (input: { zipFile: File | null; dirPath: string; overwrite: boolean }) => void;
}) {
  const { t } = useTranslation('settings');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipKey, setZipKey] = useState(0);
  const [dirPath, setDirPath] = useState('');
  const [overwrite, setOverwrite] = useState(false);

  useEffect(() => {
    if (open) {
      setZipFile(null);
      setZipKey((k) => k + 1);
      setDirPath('');
      setOverwrite(false);
    }
  }, [open]);

  return (
    <ModalOverlay open={open} onClose={onClose}>
      <div
        className="modal glass-card glass-card--dialog plugin-install-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('plugins.install')}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mcp-dialog__title">{t('plugins.install')}</h3>
        <p className="muted small">{t('plugins.empty')}</p>
        <div className="field-group">
          <label className="field-label" htmlFor="plugin-zip">
            {t('plugins.zipAria')}
          </label>
          <input
            id="plugin-zip"
            type="file"
            accept=".zip"
            className="plugin-zip-input"
            aria-label={t('plugins.zipAria')}
            key={zipKey}
            disabled={busy}
            onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="plugin-dir">
            {t('plugins.dirAria')}
          </label>
          <input
            id="plugin-dir"
            className="field input"
            aria-label={t('plugins.dirAria')}
            placeholder={t('plugins.dirPlaceholder')}
            value={dirPath}
            disabled={busy}
            onChange={(e) => setDirPath(e.target.value)}
          />
        </div>
        <label className="plugin-picker-option">
          <input
            type="checkbox"
            aria-label={t('plugins.overwrite')}
            checked={overwrite}
            disabled={busy}
            onChange={(e) => setOverwrite(e.target.checked)}
          />
          {t('plugins.overwrite')}
        </label>
        <p className="muted" style={{ fontSize: 11 }}>
          {t('plugins.overwriteNote')}
        </p>
        <div className="mcp-dialog__footer">
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            aria-label={t('plugins.installAria')}
            disabled={busy || (!zipFile && !dirPath.trim())}
            onClick={() => onInstall({ zipFile, dirPath, overwrite })}
          >
            {busy ? t('plugins.installing') : t('plugins.install')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

/** Plugins: discovered from the plugins/ directory; bundle or per-item approval mounts their skills/hooks immediately, while MCP entries are only registered as pending.
 *  Two install paths are offered — a zip (shipped via /api/uploads) or a local directory — and installed plugins stay unapproved until explicitly approved;
 *  unapproved plugins can be deleted outright (approved ones must be unapproved first). */
export function PluginsBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [plugins, setPlugins] = useState<PluginItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<string | null>(null); // Plugin name currently being picked per-item
  const [installOpen, setInstallOpen] = useState(false);
  const [installing, setInstalling] = useState(false); // busy flag against double submits

  const reload = () =>
    listPlugins<PluginItem>()
      .then((items) => {
        setPlugins(items);
        setLoadFailed(false);
      })
      .catch(() => undefined); // Post-action refresh failure: keep the current list silently; toasts are the caller's job

  useEffect(() => {
    let alive = true;
    listPlugins<PluginItem>()
      .then((items) => {
        if (alive) setPlugins(items);
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
    if (!q) return plugins ?? [];
    return (plugins ?? []).filter(
      (p) => p.name.toLowerCase().includes(q) || (p.description ?? '').toLowerCase().includes(q)
    );
  }, [plugins, search]);

  const run = async (verb: ApprovalVerb, p: PluginItem, args: Record<string, unknown>) => {
    setBusyName(p.name);
    try {
      const res = (await setPluginApproval({
        name: p.name,
        approved: verb !== 'revoke',
        ...args,
      })) as PluginApproveResult;
      addToast({ type: 'success', message: resultMessage(verb, res) });
      setEditing(null);
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('plugins.actionFailed', {
          verb: t(verb === 'revoke' ? 'plugins.verb.revoke' : 'plugins.verb.approve'),
          message: extractErrorMessage(err),
        }),
      });
    } finally {
      setBusyName(null);
    }
  };

  const onInstall = async (input: {
    zipFile: File | null;
    dirPath: string;
    overwrite: boolean;
  }) => {
    if (installing || (!input.zipFile && !input.dirPath.trim())) return;
    if (input.overwrite && !(await confirmDialog({ message: t('plugins.overwriteConfirm') })))
      return;
    setInstalling(true);
    try {
      // Zips go through the existing upload transport (/api/uploads -> workspace/imports), which returns a server-side path;
      // directories pass the user-pasted absolute path directly; source legitimacy is validated by the backend against allowed roots
      const args = input.zipFile
        ? { zip_path: (await uploadFile(input.zipFile)).file_path, overwrite: input.overwrite }
        : { source_dir: input.dirPath.trim(), overwrite: input.overwrite };
      const res = (await installPlugin(args)) as PluginInstallResult;
      addToast({
        type: 'success',
        message: t('plugins.installed', {
          name: res.name,
          version: res.version ? ` v${res.version}` : '',
        }),
      });
      setInstallOpen(false);
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('plugins.installFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setInstalling(false);
    }
  };

  const onDelete = async (p: PluginItem) => {
    if (
      !(await confirmDialog({
        message: t('plugins.deleteConfirm', { name: p.name, path: p.path }),
        danger: true,
      }))
    )
      return;
    setBusyName(p.name);
    try {
      await uninstallPlugin(p.name);
      addToast({ type: 'success', message: t('plugins.deleted', { name: p.name }) });
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('plugins.deleteFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyName(null);
    }
  };

  const onUnapprove = async (p: PluginItem) => {
    // Unapproving reclaims the plugin's registered external MCP servers that have no approved tools;
    // servers with approved tools or shared with other plugins are kept by the backend, with the outcome disclosed in the toast. The confirm dialog lists the reclaim candidates.
    const reclaimable = p.mcp
      .filter((m) => m.registered && m.tools_approved.length === 0)
      .map((m) => m.id);
    const note =
      reclaimable.length > 0 ? t('plugins.revokeNote', { list: reclaimable.join('、') }) : '';
    if (
      !(await confirmDialog({
        message: t('plugins.revokeConfirm', { name: p.name, note }),
        danger: true,
      }))
    )
      return;
    void run('revoke', p, { granularity: 'bundle' });
  };

  const onItem = (p: PluginItem, picks: PluginPicks) =>
    void run('approve', p, {
      granularity: 'item',
      skills: picks.skills,
      hooks: picks.hooks,
      mcp: picks.mcp,
    });

  if (loadFailed) {
    return (
      <EmptyState
        title={t('plugins.loadFailedTitle')}
        description={t('common.loadFailed')}
        icon={EmptyStateIcons.warning}
        onRetry={() => void reload()}
      />
    );
  }
  if (plugins === null) {
    return <LoadingSpinner label={t('plugins.loading')} />;
  }

  return (
    <div className="plugins-block">
      <SettingsToolbar
        countLabel={t('plugins.installed')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('plugins.searchPlaceholder')}
        actions={
          <button
            type="button"
            className="btn btn-primary btn-sm"
            aria-label={t('plugins.installAria')}
            onClick={() => setInstallOpen(true)}
          >
            + {t('plugins.install')}
          </button>
        }
      />

      {filtered.length === 0 ? (
        plugins.length === 0 ? (
          <EmptyState
            title={t('plugins.emptyTitle')}
            description={t('plugins.empty')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <p className="muted small">{t('plugins.searchEmpty')}</p>
        )
      ) : (
        <ul className="settings-rows">
          {filtered.map((p) => {
            const expanded = editing === p.name;
            return (
              <li key={p.path} className="settings-row entity-row plugin-row">
                <span className="entity-icon" style={{ '--h': nameHue(p.name) } as CSSProperties}>
                  {p.name.slice(0, 1).toUpperCase()}
                </span>
                <button
                  type="button"
                  className="entity-row__main entity-row__open"
                  aria-expanded={expanded}
                  aria-label={t('plugins.editAria', { name: p.name })}
                  onClick={() => setEditing(expanded ? null : p.name)}
                >
                  <span className="entity-row__title">
                    <span className="entity-row__name">
                      {p.name}
                      {p.version ? ` v${p.version}` : ''}
                    </span>
                    <span className="chip">
                      {p.approved
                        ? t(
                            p.granularity === 'item'
                              ? 'plugins.approvedItem'
                              : 'plugins.approvedBundle'
                          )
                        : t('plugins.notApproved')}
                    </span>
                    <span className="entity-row__meta">
                      {t('plugins.contains', {
                        skills: p.contains.skills,
                        hooks: p.contains.hooks,
                      })}
                      {p.contains.mcp ? t('plugins.containsMcp') : ''}
                    </span>
                  </span>
                  {p.description && <span className="entity-row__desc">{p.description}</span>}
                  <span className="entity-row__meta">
                    {t('plugins.requestPermission')}
                    {permissionSummary(p)}
                  </span>
                </button>
                <div className="entity-row__actions">
                  <Switch
                    checked={p.approved}
                    small
                    disabled={busyName === p.name}
                    ariaLabel={
                      p.approved
                        ? t('plugins.unapproveAria', { name: p.name })
                        : t('plugins.approveBundleAria', { name: p.name })
                    }
                    onChange={(checked) =>
                      checked ? void run('approve', p, { granularity: 'bundle' }) : onUnapprove(p)
                    }
                  />
                  {!p.approved && (
                    <button
                      type="button"
                      className="llm-icon-btn is-danger"
                      aria-label={t('plugins.deleteAria', { name: p.name })}
                      disabled={busyName === p.name}
                      onClick={() => void onDelete(p)}
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
                  )}
                </div>
                {expanded && (
                  <PluginPicker
                    p={p}
                    busy={busyName === p.name}
                    onCancel={() => setEditing(null)}
                    onSubmit={(picks) => onItem(p, picks)}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}

      <PluginInstallDialog
        open={installOpen}
        busy={installing}
        onClose={() => setInstallOpen(false)}
        onInstall={(input) => void onInstall(input)}
      />
    </div>
  );
}
