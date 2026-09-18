/**
 * @file SubagentsSection
 * @description Settings "子代理" section: searchable definition roster with a
 * 10-row collapse, per-row enable toggle and delete, and create/edit via the
 * SubagentDialog (the reference settings layout: count + search + 新建, then
 * one row per definition with chips, description, switch and delete).
 *
 * Running instances and resumable checkpoints stay in their own sections
 * (InstanceList / ResumableList), which render below this manager.
 */

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { deleteSubagent, listPersonas, listSubagents, listTools, registerSubagent } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Switch } from '@/components/common/Switch';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import { extractErrorMessage } from '@/utils/errors';
import { notifyTeamDefsChanged, onTeamDefsChanged } from '@/components/team/defsEvents';
import { SubagentDialog } from '@/components/team/SubagentDialog';
import { modeLabel } from '@/components/team/constants';
import type { PersonaItem, SubagentDef, ToolItem } from '@/components/team/types';

/** Rows visible before the "show all" expander kicks in. */
const VISIBLE_CAP = 10;

/** Deterministic hue from the definition name: stable row icon color without storing one. */
function nameHue(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) % 360;
  return hash;
}

export function SubagentsSection() {
  const { t } = useTranslation('team');
  const addToast = useUIStore((s) => s.addToast);
  const [definitions, setDefinitions] = useState<SubagentDef[] | null>(null);
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<SubagentDef | null>(null);
  const [tools, setTools] = useState<ToolItem[] | null>(null); // lazy: loaded when the dialog first opens
  const [deleteTarget, setDeleteTarget] = useState<SubagentDef | null>(null);
  const [busyName, setBusyName] = useState('');

  const load = async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    if (!silent) setDefinitions(null);
    try {
      const [sub, personasArr] = await Promise.all([listSubagents(), listPersonas<PersonaItem>()]);
      setDefinitions((sub.definitions as SubagentDef[]) ?? []);
      setPersonas(personasArr);
      setLoadError('');
    } catch (err) {
      setLoadError(extractErrorMessage(err));
    }
  };

  useEffect(() => {
    void load();
    return onTeamDefsChanged(() => {
      void load({ silent: true });
    });
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return definitions ?? [];
    return (definitions ?? []).filter(
      (d) =>
        d.name.toLowerCase().includes(q) || (d.description ?? '').toLowerCase().includes(q)
    );
  }, [definitions, search]);

  const openCreate = async () => {
    if (tools === null) {
      try {
        setTools(await listTools<ToolItem>());
      } catch (err) {
        addToast({
          type: 'error',
          message: t('team:tool.loadFailedToast', { message: extractErrorMessage(err) }),
        });
        return;
      }
    }
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (def: SubagentDef) => {
    void (async () => {
      if (tools === null) {
        try {
          setTools(await listTools<ToolItem>());
        } catch {
          // The picker degrades to name-less entries; editing tool selection still works on saved names
        }
      }
      setEditing(def);
      setDialogOpen(true);
    })();
  };

  const toggleEnabled = async (def: SubagentDef) => {
    setBusyName(def.name);
    try {
      await registerSubagent({
        name: def.name,
        description: def.description,
        mode: def.mode,
        persona: def.persona,
        allowed_tools: def.allowed_tools ?? undefined,
        max_rounds: def.max_rounds ?? undefined,
        max_tool_calls: def.max_tool_calls ?? undefined,
        network_mode: def.network_mode || undefined,
        readonly: def.readonly ?? false,
        enabled: !(def.enabled ?? true),
      });
      await load({ silent: true });
      notifyTeamDefsChanged();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:spawn.toast.failed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyName('');
    }
  };

  const doDelete = async (def: SubagentDef) => {
    setBusyName(def.name);
    try {
      await deleteSubagent(def.name);
      addToast({ type: 'success', message: t('team:mgr.deleted', { name: def.name }) });
      setDeleteTarget(null);
      await load({ silent: true });
      notifyTeamDefsChanged();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:mgr.deleteFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyName('');
      setDeleteTarget(null);
    }
  };

  if (definitions === null && !loadError) {
    return <LoadingSpinner label={t('team:def.loading')} />;
  }
  if (loadError) {
    return (
      <EmptyState
        title={t('team:def.loadFailed')}
        description={loadError}
        icon={EmptyStateIcons.warning}
        onRetry={() => void load()}
      />
    );
  }

  const visible = expanded || search.trim() ? filtered : filtered.slice(0, VISIBLE_CAP);
  const hiddenCount = filtered.length - visible.length;

  return (
    <div className="subagents-manager">
      <SettingsToolbar
        countLabel={t('team:mgr.installed')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('team:mgr.searchPlaceholder')}
        actions={
          <>
            <button
              type="button"
              className="llm-icon-btn"
              aria-label={t('team:mgr.refresh')}
              onClick={() => void load()}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                <path d="M21 3v6h-6" />
              </svg>
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void openCreate()}>
              + {t('team:mgr.create')}
            </button>
          </>
        }
      />

      {filtered.length === 0 ? (
        search.trim() ? (
          <p className="muted small">{t('team:mgr.searchEmpty')}</p>
        ) : (
          <EmptyState
            title={t('team:def.empty.title')}
            description={t('team:mgr.emptyDescription')}
            icon={EmptyStateIcons.team}
          />
        )
      ) : (
        <ul className="settings-rows">
          {visible.map((d) => {
            const enabled = d.enabled ?? true;
            return (
              <li key={d.name} className={`settings-row entity-row${enabled ? '' : ' is-disabled'}`}>
                <span className="entity-icon" style={{ '--h': nameHue(d.name) } as CSSProperties}>
                  {d.name.slice(0, 1).toUpperCase()}
                </span>
                <button
                  type="button"
                  className="entity-row__main entity-row__open"
                  onClick={() => openEdit(d)}
                  aria-label={t('team:mgr.editAria', { name: d.name })}
                >
                  <span className="entity-row__title">
                    <span className="entity-row__name mono">{d.name}</span>
                    <span className="chip">{modeLabel(t, d.mode)}</span>
                    {d.readonly ? <span className="chip">{t('team:mgr.readonlyChip')}</span> : null}
                    <span className="chip">
                      {d.allowed_tools
                        ? t('team:mgr.toolsCount', { n: d.allowed_tools.length })
                        : t('team:mgr.allTools')}
                    </span>
                    {!enabled ? <span className="chip">{t('team:mgr.disabled')}</span> : null}
                  </span>
                  {d.description && <span className="entity-row__desc">{d.description}</span>}
                </button>
                <div className="entity-row__actions">
                  <Switch
                    checked={enabled}
                    small
                    disabled={busyName === d.name}
                    ariaLabel={t('team:mgr.enabledAria', { name: d.name })}
                    onChange={() => void toggleEnabled(d)}
                  />
                  <button
                    type="button"
                    className="llm-icon-btn is-danger"
                    aria-label={t('team:mgr.deleteAria', { name: d.name })}
                    disabled={busyName === d.name}
                    onClick={() => setDeleteTarget(d)}
                  >
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M3 6h18" />
                      <path d="M8 6V4h8v2" />
                      <path d="M6 6l1 14h10l1-14" />
                    </svg>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {hiddenCount > 0 && (
        <button
          type="button"
          className="settings-rows__more"
          onClick={() => setExpanded(true)}
        >
          {t('team:mgr.showAll', { n: hiddenCount })}
        </button>
      )}
      {expanded && filtered.length > VISIBLE_CAP && !search.trim() && (
        <button type="button" className="settings-rows__more" onClick={() => setExpanded(false)}>
          {t('team:mgr.collapse')}
        </button>
      )}

      {/* Keyed by target: each open mounts a fresh dialog seeded from the
          editing target (no stale-form flash between opens) */}
      <SubagentDialog
        key={editing?.name ?? '__new__'}
        open={dialogOpen}
        editing={editing}
        personas={personas}
        tools={tools ?? []}
        existingNames={(definitions ?? []).map((d) => d.name)}
        onClose={() => {
          setDialogOpen(false);
          setEditing(null);
        }}
        onSaved={() => {
          void load({ silent: true });
          notifyTeamDefsChanged();
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('team:mgr.deleteTitle')}
        message={t('team:mgr.deleteConfirm', { name: deleteTarget?.name ?? '' })}
        confirmLabel={t('settings:common.delete')}
        danger
        onConfirm={() => deleteTarget && void doDelete(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
