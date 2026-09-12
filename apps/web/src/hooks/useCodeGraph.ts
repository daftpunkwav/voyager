/**
 * @file useCodeGraph
 * @description Code-graph hooks: index status polling, graph fetching and
 * trigger/refresh/delete index mutations.
 *
 * Responsibilities:
 * - Poll per-project index status every 2s while a job is QUEUED/CLONING/
 *   INDEXING, reusing the api-level status vocabulary
 * - Fetch the project subgraph and convert it to render data (toRenderGraph)
 * - Wrap trigger/refresh/delete mutations with status and graph query
 *   invalidation, including the global index admin list on delete
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listCodeGraphIndexStatuses,
  getCodeGraph,
  triggerCodeGraphIndex,
  refreshCodeGraphIndex,
  deleteCodeGraphIndex,
} from '@/api/codeGraph';
import { i18n } from '@/i18n';
import type { GraphIndexStatus } from '@/components/code-graph/types';
import { toRenderGraph } from '@/components/code-graph/renderGraph';

function requireProjectId(projectId: string | undefined): string {
  if (!projectId) throw new Error(i18n.t('codeGraph:error.missingProjectIdParam'));
  return projectId;
}

/** Project index status: the newest list_index_jobs row for this project.
 *  Status vocabulary is normalized in api/codeGraph; this hook keeps no second mapping. */
export function useIndexStatus(projectId: string | undefined) {
  return useQuery({
    queryKey: ['graph-index-status', projectId],
    enabled: Boolean(projectId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (s && ['QUEUED', 'CLONING', 'INDEXING'].includes(s)) return 2000;
      return false;
    },
    queryFn: async () => {
      const { items } = await listCodeGraphIndexStatuses();
      const mine = items
        .filter((r) => r.project_id === projectId)
        .sort((a, b) => Number(b.created_ts ?? 0) - Number(a.created_ts ?? 0));
      const row = mine[0];
      return {
        project_id: projectId,
        engine_project: row?.engine_project ?? '',
        status: row ? row.status : 'NONE',
        error: row?.error ?? null,
      } as GraphIndexStatus;
    },
  });
}

export function useCodeGraph(
  projectId: string | undefined,
  opts: { maxNodes: number; enabled: boolean }
) {
  return useQuery({
    queryKey: ['code-graph', projectId, opts.maxNodes],
    enabled: Boolean(projectId) && opts.enabled,
    queryFn: async () => {
      const res = await getCodeGraph(requireProjectId(projectId), {
        max_nodes: opts.maxNodes,
      });
      return { data: res, render: toRenderGraph(res) };
    },
  });
}

export function useTriggerIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void }
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: 'fast' | 'moderate' | 'full' = 'moderate') => {
      return triggerCodeGraphIndex(requireProjectId(projectId), { mode });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
    },
    onError: opts?.onError,
  });
}

export function useRefreshIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void }
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: 'fast' | 'moderate' | 'full' = 'moderate') => {
      return refreshCodeGraphIndex(requireProjectId(projectId), { mode });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
    },
    onError: opts?.onError,
  });
}

export function useDeleteIndex(
  projectId: string | undefined,
  opts?: { onError?: (err: Error) => void }
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      return deleteCodeGraphIndex(requireProjectId(projectId));
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['graph-index-status', projectId] });
      void qc.invalidateQueries({ queryKey: ['code-graph', projectId] });
      // Plural key = the global index admin list (GraphIndexProgressBar); a separate query from the per-project one
      void qc.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: opts?.onError,
  });
}

export type { GraphIndexStatus };
