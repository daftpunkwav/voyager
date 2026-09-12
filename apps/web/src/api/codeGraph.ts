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
 *   vocabulary (the single mapping point for consumers)
 * - Wrap the index lifecycle: enqueue/refresh, cancel, drop and batch index
 * - Fetch repository subgraphs (get_subgraph) as the shared RawSubgraph shape
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';

/** Raw return shape of get_subgraph (shared with toRenderGraph as its input). */
export interface RawSubgraph {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  stats?: { node_count?: number; edge_count?: number; total_nodes?: number };
}

/** Index job row (mapped shape of list_index_jobs for the UI vocabulary). */
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
 *  the vocabulary only requires touching this file, so consumers never drift. */
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
 *  vocabulary (rows may arrive as a bare array and use lowercase statuses). */
export async function listCodeGraphIndexStatuses(): Promise<{ items: CodeGraphIndexJob[] }> {
  const rows = await callCapability<Record<string, unknown>[]>('graph', 'list_index_jobs', {});
  const list = Array.isArray(rows) ? rows : [];
  const items = list.map((r) => ({
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

export function cancelCodeGraphIndex(projectId: string): Promise<unknown> {
  return callCapability('graph', 'cancel_index', { project: projectId }).then(unwrapDataField);
}

/** Trigger indexing (mode: fast|moderate|full). */
export function triggerCodeGraphIndex(
  projectId: string,
  b?: { mode?: 'fast' | 'moderate' | 'full' }
): Promise<unknown> {
  return callCapability('graph', 'enqueue_index', { project: projectId, ...b }).then(
    unwrapDataField
  );
}

/** Rebuild index (same capability as trigger; semantic alias kept for call-site readability). */
export function refreshCodeGraphIndex(
  projectId: string,
  b?: { mode?: 'fast' | 'moderate' | 'full' }
): Promise<unknown> {
  return callCapability('graph', 'enqueue_index', { project: projectId, ...b }).then(
    unwrapDataField
  );
}

export function deleteCodeGraphIndex(projectId: string): Promise<unknown> {
  return callCapability('graph', 'drop_project_graph', { project: projectId }).then(
    unwrapDataField
  );
}

export function getCodeGraph(projectId: string, p?: { max_nodes?: number }): Promise<RawSubgraph> {
  return callCapability('graph', 'get_subgraph', { project: projectId, ...p }).then((r) =>
    unwrapDataField<RawSubgraph>(r)
  );
}

export function batchIndexCodeGraph(
  ids: string[],
  mode?: 'fast' | 'moderate' | 'full'
): Promise<unknown> {
  return callCapability('graph', 'enqueue_index', { project_ids: ids, mode }).then(unwrapDataField);
}
