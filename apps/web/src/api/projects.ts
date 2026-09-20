/**
 * @file projects.ts
 * @description Project domain: the repo resources of the sources service.
 *
 * The current model has no project/category/tag entities: categories and tags
 * are string fields on resources, and projects come from imports. list_repos
 * only honors sort/desc/category; search, progress/tag filtering and
 * pagination are filled in client-side (adequate for personal-scale data).
 * All functions return payloads directly, without a {data} envelope.
 *
 * Responsibilities:
 * - Fill list_repos gaps client-side: search, language/progress/tag
 *   filtering and pagination
 * - Run serial batch imports (import_repo per URL) and aggregate
 *   ok/failed results with localized error copy
 * - Aggregate stats and tag usage from live repo rows
 * - Wrap repo meta mutations (progress / tags / category) and JSON export
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, ServiceError, unwrapDataField } from '@/bridge/client';
import { i18n } from '@/i18n';
import type { PaginatedList, Project, ProjectListParams, ProjectReadme, Tag } from '@/api/types';

type RepoRow = Record<string, unknown>;

/** Batch import: submits import_repo(url) once per item, serially — import_repo
 *  is a single-item async capability that returns a JobRef. Resolves
 *  {ok, failed, errors, summary} for the import dialog. */
export async function importProjects(r: unknown): Promise<{
  ok: number;
  failed: number;
  errors: string[];
  summary: string;
}> {
  const repos = Array.isArray(r) ? (r as Array<{ url?: string }>) : [];
  let ok = 0;
  const errors: string[] = [];
  for (const item of repos) {
    const url = String(item?.url ?? '');
    if (!url) {
      errors.push(i18n.t('sources:api.emptyUrl'));
      continue;
    }
    try {
      await callCapability('sources', 'import_repo', { url });
      ok += 1;
    } catch (err) {
      errors.push(
        err instanceof ServiceError
          ? `${url}: ${err.message}`
          : i18n.t('sources:api.importFailed', { url })
      );
    }
  }
  return {
    ok,
    failed: errors.length,
    errors,
    summary: i18n.t('sources:api.importSubmitted', { count: ok }),
  };
}

/** Frontend sort keys → backend list_repos sort keys (RepoStore._SORTABLE:
 *  unknown keys silently fall back to added_ts). */
const SORT_PARAM: Record<NonNullable<ProjectListParams['sort_by']>, string> = {
  name: 'name',
  stars: 'stars',
  imported_at: 'added',
  updated_at: 'updated',
};

/** List: the server only applies sort/desc/category; remaining filtering and pagination happen client-side. */
export async function listProjects(p?: ProjectListParams): Promise<PaginatedList<Project>> {
  const rows = await callCapability<RepoRow[]>('sources', 'list_repos', {
    sort: SORT_PARAM[p?.sort_by ?? 'imported_at'],
    desc: (p?.sort_order ?? 'desc') !== 'asc',
    category: p?.category_id ?? '',
  });
  let items = Array.isArray(rows) ? rows : [];
  const q = (p?.search ?? '').trim().toLowerCase();
  if (q) {
    items = items.filter((it) =>
      `${it.full_name ?? ''}${it.name ?? ''}${it.description ?? ''}`.toLowerCase().includes(q)
    );
  }
  if (p?.language) items = items.filter((it) => it.language === p.language);
  if (p?.progress) items = items.filter((it) => it.progress === p.progress);
  if (p?.tag_id) {
    items = items.filter(
      (it) => Array.isArray(it.tags) && (it.tags as string[]).includes(p.tag_id as string)
    );
  }
  const total = items.length;
  const page = Math.max(1, p?.page ?? 1);
  const pageSize = Math.max(1, p?.page_size ?? total);
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize) as unknown as Project[],
    total,
    page,
    page_size: pageSize,
  };
}

export function getProject(id: string): Promise<Project> {
  return callCapability('sources', 'get_repo', { repo_id: id }).then(unwrapDataField<Project>);
}

export function getProjectReadme(id: string): Promise<ProjectReadme> {
  return callCapability('sources', 'get_readme', { repo_id: id }).then(
    unwrapDataField<ProjectReadme>
  );
}

export function updateProject(id: string, d: Record<string, unknown>): Promise<unknown> {
  return callCapability('sources', 'set_repo_meta', { repo_id: id, ...d }).then(unwrapDataField);
}

export function deleteProject(id: string): Promise<unknown> {
  return callCapability('sources', 'remove_repo', { repo_id: id }).then(unwrapDataField);
}

export function updateProgress(id: string, progress: unknown): Promise<unknown> {
  return callCapability('sources', 'set_repo_meta', { repo_id: id, progress }).then(
    unwrapDataField
  );
}

/** Stats aggregated from live list_repos data. */
export async function getProjectStats(): Promise<{
  total: number;
  by_progress: Record<string, number>;
}> {
  const rows = await callCapability<RepoRow[]>('sources', 'list_repos', {});
  const list = Array.isArray(rows) ? rows : [];
  const by: Record<string, number> = { none: 0, learning: 0, learned: 0, mastered: 0 };
  for (const it of list) {
    const key = String(it.progress ?? 'none');
    by[key] = (by[key] ?? 0) + 1;
  }
  return { total: list.length, by_progress: by };
}

/** Export = current resource list as JSON (raw list_repos output). */
export function exportProjects(): Promise<RepoRow[]> {
  return callCapability('sources', 'list_repos', {}).then(unwrapDataField<RepoRow[]>);
}

/** Categories: plain string fields on resources in the current model; the backend returns a bare string array. */
export function listCategories(): Promise<string[]> {
  return callCapability('sources', 'list_categories', {}).then(unwrapDataField<string[]>);
}

/** Tags aggregated from each resource's tags string field (tags are not entities);
 *  count is usage and id equals the name, so the edit-dialog checkbox value is the
 *  tag name and can be stored directly via setProjectTags. */
export async function listTags(): Promise<Tag[]> {
  const rows = await callCapability<RepoRow[]>('sources', 'list_repos', {});
  const list = Array.isArray(rows) ? rows : [];
  const counts = new Map<string, number>();
  for (const it of list) {
    if (!Array.isArray(it.tags)) continue;
    for (const t of it.tags as unknown[]) {
      const name = String(t).trim();
      if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, count]) => ({ id: name, name, count }));
}

/** Tags are plain strings: checked tag names are stored as-is via set_repo_meta. */
export function setProjectTags(projectId: string, tags: string[]): Promise<unknown> {
  return callCapability('sources', 'set_repo_meta', { repo_id: projectId, tags }).then(
    unwrapDataField
  );
}

export function searchGithubRepos(query: string): Promise<unknown> {
  return callCapability('sources', 'search_remote_repos', { query }).then(unwrapDataField);
}
