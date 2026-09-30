/**
 * @file codeGraph.ts
 * @description Code-graph domain (L1): repository structure index management.
 *
 * Carried by the graph service and consumed only by the code-graph page
 * domain; the L0 universe view lives in api/graph.ts. All functions return
 * payloads directly.
 *
 * Responsibilities:
 * - Map raw list_index_jobs rows onto the canonical CodeGraphIndexJobStatus
 *   vocabulary (the single mapping point for consumers); L0 relation jobs are
 *   excluded — this facade is the L1 repo-index surface only
 * - Wrap the index lifecycle against the frozen graph capability signatures:
 *   enqueue_index(project, repo_path, priority) / cancel_index(job_id) /
 *   drop_project_graph(project); repo_path is resolved from the sources repo
 *   row (the clone lands under workspace/repo, inside the graph path jail)
 * - Fetch a project graph via query_graph and normalize it to the shared
 *   RawSubgraph shape (store edge rows use src/dst; the renderer wants
 *   source/target — the mapping happens here, nowhere else)
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability } from '@/bridge/client';
import { getProject } from '@/api/projects';
import { i18n } from '@/i18n';

/** Raw return shape shared with toRenderGraph as its input. Nodes carry the
 *  store row fields merged with their attrs JSON; edges are normalized to
 *  source/target from the store's src/dst columns. */
export interface RawSubgraph {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  stats?: { node_count?: number; edge_count?: number; total_nodes?: number };
}

/** Index job row (mapped shape of list_index_jobs for the UI vocabulary).
 *  engine_project carries the backend repo_path (the local clone directory). */
export interface CodeGraphIndexJob {
  id: string;
  project_id: string;
  engine_project: string;
  status: CodeGraphIndexJobStatus;
  error?: string;
  created_ts: number;
  updated_ts: number;
}

/** Canonical status vocabulary for index jobs, aligned with GraphIndexStatus
 *  (components/code-graph/types). This is the single mapping point: changing
 *  the vocabulary only requires touching this file, so consumers never drift.
 *  The queue produces queued/running/done/failed/cancelled; CLONING and READY
 *  are kept for engine-specific rows. */
export type CodeGraphIndexJobStatus =
  'QUEUED' | 'CLONING' | 'INDEXING' | 'READY' | 'STALE' | 'CLONE_FAILED' | 'INDEX_FAILED';

const JOB_STATUS_MAP: Record<string, CodeGraphIndexJobStatus> = {
  QUEUED: 'QUEUED',
  CLONING: 'CLONING',
  RUNNING: 'INDEXING',
  DONE: 'READY',
  READY: 'READY',
  CANCELLED: 'STALE',
  CLONE_FAILED: 'CLONE_FAILED',
  INDEX_FAILED: 'INDEX_FAILED',
  FAILED: 'INDEX_FAILED',
};

/** Index job list: maps raw list_index_jobs rows onto the canonical status
 *  vocabulary (rows may arrive as a bare array and use lowercase statuses).
 *  L0 relation-analysis rows (level="l0", project="universe") are not repo
 *  index jobs and never enter this facade. */
export async function listCodeGraphIndexStatuses(): Promise<{ items: CodeGraphIndexJob[] }> {
  const rows = await callCapability<Record<string, unknown>[]>('graph', 'list_index_jobs', {});
  const list = Array.isArray(rows) ? rows : [];
  const items = list
    .filter((r) => r.level !== 'l0')
    .map((r) => ({
      id: String(r.id ?? ''),
      project_id: String(r.project ?? ''),
      engine_project: String(r.repo_path ?? ''),
      // Unknown statuses surface in the failed tab instead of vanishing silently
      status: JOB_STATUS_MAP[String(r.status ?? '').toUpperCase()] ?? 'INDEX_FAILED',
      error: r.error ? String(r.error) : undefined,
      created_ts: Number(r.created_ts ?? 0),
      updated_ts: Number(r.updated_ts ?? 0),
    }));
  return { items };
}

/** Cancel a queued index job by its queue id (cancel_index(job_id)); the
 *  backend refuses running jobs with CONFLICT — only QUEUED rows qualify. */
export function cancelCodeGraphIndex(jobId: string): Promise<unknown> {
  return callCapability('graph', 'cancel_index', { job_id: jobId });
}

/** Resolve the workspace-local clone path for a repo resource; enqueue_index
 *  requires it (repo_path) and rejects paths outside the workspace jail. */
async function resolveRepoPath(projectId: string): Promise<string> {
  const repo = (await getProject(projectId)) as { local_path?: unknown };
  const repoPath = String(repo.local_path ?? '');
  if (!repoPath) {
    throw new Error(i18n.t('errors:graph.noLocalClone'));
  }
  return repoPath;
}

/** Trigger indexing: enqueue_index(project, repo_path, priority). The backend
 *  has no index-mode parameter (the pipeline always runs its default mode). */
export async function triggerCodeGraphIndex(
  projectId: string,
  opts?: { priority?: number }
): Promise<unknown> {
  const repo_path = await resolveRepoPath(projectId);
  return callCapability('graph', 'enqueue_index', {
    project: projectId,
    repo_path,
    ...(opts?.priority !== undefined ? { priority: opts.priority } : {}),
  });
}

/** Rebuild index (same capability as trigger; semantic alias kept for call-site readability). */
export function refreshCodeGraphIndex(
  projectId: string,
  opts?: { priority?: number }
): Promise<unknown> {
  return triggerCodeGraphIndex(projectId, opts);
}

export function deleteCodeGraphIndex(projectId: string): Promise<unknown> {
  return callCapability('graph', 'drop_project_graph', { project: projectId });
}

/** Whole-project graph via query_graph (get_subgraph needs a node_id root and
 *  is not the "load everything" entry). limit maps to the backend's page cap
 *  (clamped server-side to 2000). Store edge rows use src/dst; they are
 *  normalized to source/target here so RawSubgraph consumers never see the
 *  store column names. */
export async function getCodeGraph(
  projectId: string,
  p?: { limit?: number }
): Promise<RawSubgraph> {
  const raw = await callCapability<Record<string, unknown>>('graph', 'query_graph', {
    project: projectId,
    ...(p?.limit !== undefined ? { limit: p.limit } : {}),
  });
  const nodes = Array.isArray(raw.nodes) ? raw.nodes : [];
  const edges = Array.isArray(raw.edges) ? raw.edges : [];
  return {
    // Merge the attrs JSON onto the row: engine-written fields (file_path,
    // status, layout hints) live there, and renderers read them top-level.
    nodes: nodes.map((n) => {
      const row = n as Record<string, unknown>;
      const attrs = row.attrs;
      return typeof attrs === 'object' && attrs !== null
        ? { ...(attrs as Record<string, unknown>), ...row }
        : row;
    }),
    edges: edges.map((e) => {
      const row = e as Record<string, unknown>;
      return {
        ...row,
        source: row.source ?? row.src,
        target: row.target ?? row.dst,
      };
    }),
  };
}

/** Batch trigger: one enqueue_index per project (the backend has no batch
 *  parameter). Serial, like importProjects; per-project failures are
 *  collected so one bad clone does not abort the rest. */
export async function batchIndexCodeGraph(
  ids: string[]
): Promise<{ queued: string[]; failed: string[] }> {
  const queued: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await triggerCodeGraphIndex(id);
      queued.push(id);
    } catch {
      failed.push(id);
    }
  }
  return { queued, failed };
}
