/**
 * @file useProjects
 * @description Data hooks for the project (sources/repo) domain: list, detail,
 * category/tag lookups, import and mutations.
 *
 * Responsibilities:
 * - Drive the project list from the filter store's params (shallow-selected
 *   so object identity stays stable)
 * - Wrap project mutations (meta, progress, tags, delete, import) with
 *   targeted list/detail/overview invalidations
 * - Run bulk operations in concurrent chunks with a single end-of-run
 *   invalidation, returning the failure count
 * - Map plain-string categories to {id, name} rows and derive the language
 *   facet from the loaded list
 */

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useShallow } from 'zustand/react/shallow';
import {
  importProjects,
  listProjects,
  getProject,
  getProjectReadme,
  updateProject,
  deleteProject,
  updateProgress,
  getProjectStats,
  listCategories,
  listTags,
  setProjectTags,
} from '@/api/projects';
import type { Project, ProjectProgress, ProjectReadme } from '@/api/types';
import { useProjectStore } from '@/stores/projectStore';
import { invalidateOverviewQueries } from '@/utils/invalidateOverview';

/** Derive query params from the store; useShallow is required so a new object
 * identity does not trigger infinite re-renders. */
function useProjectListParams() {
  return useProjectStore(
    useShallow((s) => ({
      search: s.search || undefined,
      category_id: s.categoryId ?? undefined,
      language: s.language ?? undefined,
      progress: s.progress ?? undefined,
      tag_id: s.tagId ?? undefined,
      sort_by: s.sortBy,
      sort_order: s.sortOrder,
      page: s.page,
      page_size: s.pageSize,
    }))
  );
}

export function useProjects() {
  const params = useProjectListParams();
  return useQuery({
    queryKey: ['projects', params],
    queryFn: () => listProjects(params),
  });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return getProject(id);
    },
    enabled: Boolean(id),
  });
}

/** Fetch the GitHub README on demand (project detail README tab). */
export function useProjectReadme(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['projectReadme', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      // message carries a backend note (generation/fallback explanation); kept in
      // the type so components can consume it
      return (await getProjectReadme(id)) as ProjectReadme & { message?: string };
    },
    enabled: Boolean(id) && enabled,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useProjectStats() {
  return useQuery({
    queryKey: ['projectStats'],
    queryFn: () => getProjectStats(),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: async () => {
      // In the current model, categories are plain strings on resources (list_categories
      // returns distinct names), not entities; map them to {id, name} so the existing
      // filter/edit UI keeps working (id === name)
      const rows = await listCategories();
      const names = Array.isArray(rows) ? rows : [];
      return names.map((n) => ({ id: String(n), name: String(n), is_preset: false }));
    },
  });
}

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: () => listTags(),
  });
}

export function useImportProjects() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (repos: Array<{ owner: string; repo: string; url: string }>) =>
      importProjects(repos),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useUpdateProgress() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, progress }: { id: string; progress: ProjectProgress }) => {
      await updateProgress(id, progress);
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.id] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await deleteProject(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

/** Bulk operations run in concurrent chunks: per-item mutations would serialize
 *  into long waits plus a refetch storm of list/overview queries per item.
 *  Chunked concurrency + a single invalidation at the end. Returns the failure
 *  count so pages can surface it. */
const BULK_CONCURRENCY = 6;

async function runBulk(ids: string[], task: (id: string) => Promise<unknown>): Promise<number> {
  let failed = 0;
  for (let i = 0; i < ids.length; i += BULK_CONCURRENCY) {
    const chunk = ids.slice(i, i + BULK_CONCURRENCY);
    const results = await Promise.allSettled(chunk.map((id) => task(id)));
    for (const r of results) {
      if (r.status === 'rejected') failed += 1;
    }
  }
  return failed;
}

export function useBulkDeleteProjects() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]) => ({ failed: await runBulk(ids, deleteProject) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useBulkMarkLearning() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]) => ({
      failed: await runBulk(ids, (id) => updateProgress(id, 'learning')),
    }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<Project> }) => {
      return updateProject(id, data);
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.id] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useSetProjectTags() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      tags,
    }: {
      projectId: string;
      /** Tag name strings (tags are not entities in the current model; set_repo_meta(tags=[...])). */
      tags: string[];
    }) => {
      return setProjectTags(projectId, tags);
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['tags'] });
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void qc.invalidateQueries({ queryKey: ['project', vars.projectId] });
    },
  });
}

export type { Project };

/** Deduplicated, sorted set of languages present in the project list; feeds the filter bar. */
export function useProjectLanguages(projects: Project[]): string[] {
  return useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      if (p.language) set.add(p.language);
    }
    return Array.from(set).sort();
  }, [projects]);
}
