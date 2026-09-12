/**
 * @file GraphIndexProgressBar
 * @description Compact index-status trigger opening a tabbed modal (ready / running / failed).
 *
 * Polls index statuses more frequently while tasks are active and provides
 * cancel, retry and delete actions with query cache invalidation.
 *
 * Responsibilities:
 * - Poll index statuses (more often while tasks are active) and open a tabbed modal
 * - Run cancel, retry and reindex mutations with query cache invalidation
 * - List per-task details under the ready / running / failed tabs
 */
import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  cancelCodeGraphIndex,
  deleteCodeGraphIndex,
  listCodeGraphIndexStatuses,
  triggerCodeGraphIndex,
} from '@/api/codeGraph';
import { getGraph } from '@/api/graph';
import { classifyErrorKind } from '@/components/graph/l0EdgeTypes';

type IndexMode = 'fast' | 'moderate' | 'full';

type IndexRow = {
  project_id: string;
  status: string;
  error?: string | null;
  error_kind?: string | null;
  index_mode?: string;
  node_count?: number | null;
  engine_project?: string;
};

type TabId = 'ready' | 'running' | 'failed';

const ACTIVE = new Set(['QUEUED', 'CLONING', 'INDEXING']);
const FAILED = new Set(['CLONE_FAILED', 'INDEX_FAILED']);

/** Status ids mapped to graph:indexStatus.* label keys; unknown ids render as-is. */
const STATUS_LABEL_KEY: Record<string, string> = {
  QUEUED: 'graph:indexStatus.QUEUED',
  CLONING: 'graph:indexStatus.CLONING',
  INDEXING: 'graph:indexStatus.INDEXING',
  READY: 'graph:indexStatus.READY',
  CLONE_FAILED: 'graph:indexStatus.CLONE_FAILED',
  INDEX_FAILED: 'graph:indexStatus.INDEX_FAILED',
};

/** Resolve a status id to its graph:indexStatus.* label; unknown ids render as-is. */
function statusLabel(t: TFunction, status: string): string {
  const key = STATUS_LABEL_KEY[status];
  return key ? t(key) : status;
}

const MODE_OPTIONS: { id: IndexMode; label: string }[] = [
  { id: 'fast', label: 'graph:indexMode.fast' },
  { id: 'moderate', label: 'graph:indexMode.moderate' },
  { id: 'full', label: 'graph:indexMode.full' },
];

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

function ModeMenu({
  disabled,
  onPick,
  label,
}: {
  disabled?: boolean;
  onPick: (mode: IndexMode) => void;
  label: string;
}) {
  const { t } = useTranslation('graph');
  const [open, setOpen] = useState(false);
  return (
    <div className="graph-index-modal__menu">
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open && (
        <div className="graph-index-modal__menu-panel" role="menu">
          {MODE_OPTIONS.map((m) => (
            <button
              key={m.id}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onPick(m.id);
              }}
            >
              {t(m.label)}
              <span className="muted">{m.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FailedRow({
  row,
  label,
  onRetry,
  onDelete,
  busy,
}: {
  row: IndexRow;
  label: string;
  onRetry: (mode: IndexMode) => void;
  onDelete: () => void;
  busy?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const { t } = useTranslation('graph');
  const kind = classifyErrorKind(row.error_kind, row.error);
  const detail = row.error?.trim() || t('graph:index.noErrorDetail');

  return (
    <li className="graph-index-modal__row is-failed">
      <div className="graph-index-modal__row-main">
        <strong>{label}</strong>
        <span className="graph-index-modal__phase">
          {statusLabel(t, row.status)}
          {row.index_mode ? ` · ${row.index_mode}` : ''}
        </span>
        <button
          type="button"
          className="graph-index-modal__err-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {kind}
          <span>{expanded ? t('graph:index.collapseReason') : t('graph:index.expandReason')}</span>
        </button>
        {expanded && (
          <pre className="graph-index-modal__err" title={detail}>
            {detail}
          </pre>
        )}
      </div>
      <div className="graph-index-modal__actions">
        <ModeMenu disabled={busy} label={t('graph:index.retry')} onPick={onRetry} />
        <button type="button" className="is-danger" disabled={busy} onClick={onDelete}>
          {t('graph:action.delete')}
        </button>
      </div>
    </li>
  );
}

/** Index details: compact trigger plus a tabbed modal (ready / running / failed). */
export function GraphIndexProgressBar() {
  const qc = useQueryClient();
  const { t } = useTranslation('graph');
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<TabId>('ready');

  const q = useQuery({
    queryKey: ['graph-index-statuses'],
    queryFn: () => listCodeGraphIndexStatuses(),
    refetchInterval: (query) => {
      // listCodeGraphIndexStatuses returns {items} directly (the API layer
      // already unwraps the envelope), so no extra .data access is needed.
      const items = query.state.data?.items as IndexRow[] | undefined;
      const running = items?.some((i) => ACTIVE.has(i.status));
      return running ? 2000 : 15_000;
    },
  });

  const graphQ = useQuery({
    queryKey: ['graph-index-name-map'],
    queryFn: async () => {
      // The name map only needs repo resource nodes; request the backend cap
      // (2000) to cover as many projects as possible (l0_view only accepts kinds/limit).
      const res = (await getGraph({ limit: 2000 })) as {
        nodes?: Array<{ name?: string; qualified_name?: string }>;
      } | null;
      return res?.nodes || [];
    },
    staleTime: 60_000,
  });

  const nameById = useMemo(() => {
    // Universe resource nodes use qualified_name = "{kind}:{resourceId}"; the
    // node's internal id is unrelated to the index task's project_id. Keep only
    // repo resources and strip the prefix to map project ids to titles.
    const map = new Map<string, string>();
    for (const n of graphQ.data || []) {
      const qn = n.qualified_name ?? '';
      if (!qn.startsWith('repo:')) continue;
      map.set(qn.slice('repo:'.length), n.name ?? '');
    }
    return map;
  }, [graphQ.data]);

  const labelOf = (row: IndexRow) =>
    nameById.get(row.project_id) || row.engine_project || shortId(row.project_id);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    void qc.invalidateQueries({ queryKey: ['code-graph'] });
    void qc.invalidateQueries({ queryKey: ['graph-index-status'] });
  };

  const cancel = useMutation({
    mutationFn: (projectId: string) => cancelCodeGraphIndex(projectId),
    onSuccess: invalidate,
  });

  const del = useMutation({
    mutationFn: (projectId: string) => deleteCodeGraphIndex(projectId),
    onSuccess: invalidate,
  });

  const reindex = useMutation({
    mutationFn: ({ projectId, mode }: { projectId: string; mode: IndexMode }) =>
      triggerCodeGraphIndex(projectId, { mode }),
    onSuccess: invalidate,
  });

  const busy = cancel.isPending || del.isPending || reindex.isPending;

  const confirmDelete = (row: IndexRow, label: string) => {
    const ok = window.confirm(t('graph:delete.confirm', { name: label }));
    if (ok) del.mutate(row.project_id);
  };

  const items = useMemo(() => (q.data?.items || []) as IndexRow[], [q.data?.items]);
  // The API layer passes through {items} only; read stats defensively and fall
  // back to locally derived counts when the field is absent.
  const stats = (q.data as { stats?: { ready?: number; failed?: number } } | undefined)?.stats;

  const running = useMemo(() => items.filter((i) => ACTIVE.has(i.status)), [items]);
  const failed = useMemo(() => items.filter((i) => FAILED.has(i.status)), [items]);
  const ready = useMemo(() => items.filter((i) => i.status === 'READY'), [items]);
  const readyCount = stats?.ready ?? ready.length;
  const failedCount = stats?.failed ?? failed.length;

  const tabs: { id: TabId; label: string; count: number; tone: string }[] = [
    { id: 'ready', label: t('graph:index.tab.ready'), count: readyCount, tone: 'ok' },
    { id: 'running', label: t('graph:index.tab.running'), count: running.length, tone: 'run' },
    { id: 'failed', label: t('graph:index.tab.failed'), count: failedCount, tone: 'fail' },
  ];

  const list = tab === 'ready' ? ready : tab === 'running' ? running : failed;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const modal =
    open &&
    createPortal(
      <div
        className="graph-index-modal-backdrop"
        role="presentation"
        onClick={() => setOpen(false)}
      >
        <div
          className="graph-index-modal glass-card glass-card--dialog"
          role="dialog"
          aria-modal="true"
          aria-label={t('graph:index.title')}
          onClick={(e) => e.stopPropagation()}
        >
          <header className="graph-index-modal__head">
            <h2>{t('graph:index.title')}</h2>
            <button
              type="button"
              className="graph-index-modal__close"
              onClick={() => setOpen(false)}
              aria-label={t('graph:action.close')}
            >
              ×
            </button>
          </header>

          <div className="graph-index-modal__tabs" role="tablist">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className={`graph-index-modal__tab${tab === item.id ? ' is-active' : ''}`}
                onClick={() => setTab(item.id)}
              >
                <span className={`graph-index-modal__circle is-${item.tone}`}>{item.count}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          <div className="graph-index-modal__body" role="tabpanel">
            {q.isLoading && <p className="graph-index-modal__empty">{t('graph:index.loading')}</p>}
            {!q.isLoading && list.length === 0 && (
              <p className="graph-index-modal__empty">
                {tab === 'ready' && t('graph:index.empty.ready')}
                {tab === 'running' && t('graph:index.empty.running')}
                {tab === 'failed' && t('graph:index.empty.failed')}
              </p>
            )}
            <ul className="graph-index-modal__list">
              {list.map((row) => {
                const label = labelOf(row);
                if (tab === 'failed') {
                  return (
                    <FailedRow
                      key={row.project_id}
                      row={row}
                      label={label}
                      busy={busy}
                      onRetry={(mode) => reindex.mutate({ projectId: row.project_id, mode })}
                      onDelete={() => confirmDelete(row, label)}
                    />
                  );
                }
                return (
                  <li key={row.project_id} className={`graph-index-modal__row is-${tab}`}>
                    <div className="graph-index-modal__row-main">
                      <strong>{label}</strong>
                      <span className="graph-index-modal__phase">
                        {statusLabel(t, row.status)}
                        {row.index_mode ? ` · ${row.index_mode}` : ''}
                        {row.node_count != null
                          ? t('graph:index.nodeCount', { num: row.node_count })
                          : ''}
                      </span>
                    </div>
                    <div className="graph-index-modal__actions">
                      {tab === 'running' && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => cancel.mutate(row.project_id)}
                        >
                          {t('graph:action.cancel')}
                        </button>
                      )}
                      {tab === 'ready' && (
                        <>
                          <ModeMenu
                            disabled={busy}
                            label={t('graph:index.reindex')}
                            onPick={(mode) => reindex.mutate({ projectId: row.project_id, mode })}
                          />
                          <button
                            type="button"
                            className="is-danger"
                            disabled={busy}
                            onClick={() => confirmDelete(row, label)}
                          >
                            {t('graph:action.delete')}
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>,
      document.body
    );

  return (
    <>
      <button
        type="button"
        className="graph-index-trigger"
        onClick={() => {
          setOpen(true);
          /* Default to the ready tab; fall back to running/failed when nothing is ready. */
          setTab(
            readyCount > 0 ? 'ready' : running.length ? 'running' : failedCount ? 'failed' : 'ready'
          );
        }}
        title={t('graph:index.openTitle')}
      >
        <span className="graph-index-trigger__label">{t('graph:index.title')}</span>
        <span className="graph-index-trigger__badge is-ok" title={t('graph:index.tab.ready')}>
          {readyCount}
        </span>
        <span className="graph-index-trigger__badge is-run" title={t('graph:index.tab.running')}>
          {running.length}
        </span>
        <span className="graph-index-trigger__badge is-fail" title={t('graph:index.tab.failed')}>
          {failedCount}
        </span>
      </button>
      {modal}
    </>
  );
}
