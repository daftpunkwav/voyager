/**
 * @file PluginsBlock
 * @description Settings block for declarative plugins: discovery from the repo-root plugins/ directory, install (zip or local dir), bundle or per-item approval, and unapproval/removal.
 *
 * Approval mounts a plugin's skills and hooks immediately; bundled MCP configs are
 * only registered as pending entries. Unapproving also reclaims the plugin's
 * registered external MCP servers that have no approved tools.
 *
 * Responsibilities:
 * - List discovered plugins with permission summaries and approval state
 * - Install from a zip upload or a local directory, with an overwrite option
 * - Approve as bundle or per-item picks; unapprove and uninstall with reclaim
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { uploadFile } from '@/bridge/client';
import { installPlugin, listPlugins, setPluginApproval, uninstallPlugin } from '@/api/agent';
import { i18n } from '@/i18n';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { PluginApproveResult, PluginInstallResult, PluginItem } from './types';

/** Semantic approval verbs; display copy resolves through settings:plugins.verb.* */
type ApprovalVerb = 'approve' | 'revoke';

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

/** Plugins: discovered from the plugins/ directory; bundle or per-item approval mounts their skills/hooks immediately, while MCP entries are only registered as pending.
 *  Two install paths are offered — a zip (shipped via /api/uploads) or a local directory — and installed plugins stay unapproved until explicitly approved;
 *  unapproved plugins can be deleted outright (approved ones must be unapproved first). */
export function PluginsBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [plugins, setPlugins] = useState<PluginItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // Plugin name currently being picked per-item
  // Install wizard: zip file / directory path / overwrite toggle; zipKey resets the file input after installing
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipKey, setZipKey] = useState(0);
  const [dirPath, setDirPath] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [installing, setInstalling] = useState(false); // busy flag against double submits

  const reload = () =>
    listPlugins<PluginItem>()
      .then((items) => setPlugins(items))
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

  const onInstall = async () => {
    if (installing || (!zipFile && !dirPath.trim())) return;
    if (overwrite && !window.confirm(t('plugins.overwriteConfirm'))) return;
    setInstalling(true);
    try {
      // Zips go through the existing upload transport (/api/uploads -> workspace/imports), which returns a server-side path;
      // directories pass the user-pasted absolute path directly; source legitimacy is validated by the backend against allowed roots
      const args = zipFile
        ? { zip_path: (await uploadFile(zipFile)).file_path, overwrite }
        : { source_dir: dirPath.trim(), overwrite };
      const res = (await installPlugin(args)) as PluginInstallResult;
      addToast({
        type: 'success',
        message: t('plugins.installed', {
          name: res.name,
          version: res.version ? ` v${res.version}` : '',
        }),
      });
      setZipFile(null);
      setZipKey((k) => k + 1); // Remount the file input to clear the installed file name
      setDirPath('');
      setOverwrite(false);
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
    if (!window.confirm(t('plugins.deleteConfirm', { name: p.name, path: p.path }))) return;
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

  const onBundle = (p: PluginItem) => void run('approve', p, { granularity: 'bundle' });
  const onUnapprove = (p: PluginItem) => {
    // Unapproving reclaims the plugin's registered external MCP servers that have no approved tools;
    // servers with approved tools or shared with other plugins are kept by the backend, with the outcome disclosed in the toast. The confirm dialog lists the reclaim candidates.
    const reclaimable = p.mcp
      .filter((m) => m.registered && m.tools_approved.length === 0)
      .map((m) => m.id);
    const note =
      reclaimable.length > 0 ? t('plugins.revokeNote', { list: reclaimable.join('、') }) : '';
    if (!window.confirm(t('plugins.revokeConfirm', { name: p.name, note }))) return;
    void run('revoke', p, { granularity: 'bundle' });
  };
  const onItem = (p: PluginItem, picks: PluginPicks) =>
    void run('approve', p, {
      granularity: 'item',
      skills: picks.skills,
      hooks: picks.hooks,
      mcp: picks.mcp,
    });

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('plugins.title')}</h3>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <input
            type="file"
            accept=".zip"
            aria-label={t('plugins.zipAria')}
            key={zipKey}
            disabled={installing}
            onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
            style={{ fontSize: 12 }}
          />
          <input
            type="text"
            aria-label={t('plugins.dirAria')}
            placeholder={t('plugins.dirPlaceholder')}
            value={dirPath}
            disabled={installing}
            onChange={(e) => setDirPath(e.target.value)}
            style={{ flex: 1, minWidth: 220, fontSize: 12 }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginTop: 6,
            flexWrap: 'wrap',
          }}
        >
          <label className="plugin-picker-option" style={{ fontSize: 12, margin: 0 }}>
            <input
              type="checkbox"
              aria-label={t('plugins.overwrite')}
              checked={overwrite}
              disabled={installing}
              onChange={(e) => setOverwrite(e.target.checked)}
            />
            {t('plugins.overwrite')}
          </label>
          <span className="muted" style={{ fontSize: 11 }}>
            {t('plugins.overwriteNote')}
          </span>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            aria-label={t('plugins.installAria')}
            disabled={installing || (!zipFile && !dirPath.trim())}
            onClick={() => void onInstall()}
          >
            {installing ? t('plugins.installing') : t('plugins.install')}
          </button>
        </div>
      </div>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : plugins === null ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('plugins.loading')}
        </p>
      ) : plugins.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('plugins.empty')}
        </p>
      ) : (
        <ul className="memory-entry-list">
          {plugins.map((p) => (
            <li key={p.path} className="memory-entry">
              <span className="memory-kind">
                {p.name}
                {p.version ? ` v${p.version}` : ''}
              </span>
              {p.description && <span className="memory-entry-summary">{p.description}</span>}
              <span className="memory-entry-summary">
                {p.approved
                  ? t(p.granularity === 'item' ? 'plugins.approvedItem' : 'plugins.approvedBundle')
                  : t('plugins.notApproved')}{' '}
                · {t('plugins.requestPermission')}
                {permissionSummary(p)}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                {t('plugins.contains', { skills: p.contains.skills, hooks: p.contains.hooks })}
                {p.contains.mcp ? t('plugins.containsMcp') : ''}
              </span>
              {editing === p.name ? (
                <PluginPicker
                  p={p}
                  busy={busyName === p.name}
                  onCancel={() => setEditing(null)}
                  onSubmit={(picks) => onItem(p, picks)}
                />
              ) : (
                <div className="agent-guideline-meta">
                  {p.approved ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={t('plugins.unapproveAria', { name: p.name })}
                        disabled={busyName === p.name}
                        onClick={() => void onUnapprove(p)}
                      >
                        {t('plugins.unapprove')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={t('plugins.editAria', { name: p.name })}
                        disabled={busyName === p.name}
                        onClick={() => setEditing(p.name)}
                      >
                        {t('plugins.editItems')}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={t('plugins.approveBundleAria', { name: p.name })}
                        disabled={busyName === p.name}
                        onClick={() => void onBundle(p)}
                      >
                        {t('plugins.approveBundle')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={t('plugins.approveCustomAria', { name: p.name })}
                        disabled={busyName === p.name}
                        onClick={() => setEditing(p.name)}
                      >
                        {t('plugins.approveCustom')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        aria-label={t('plugins.deleteAria', { name: p.name })}
                        disabled={busyName === p.name}
                        onClick={() => void onDelete(p)}
                      >
                        {t('common.delete')}
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
