/**
 * @file types/sources.ts
 * @description Resource domain types: user / GitHub accounts, projects (legacy
 * Project → current Repo), categories and tags, import and indexing.
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

// ---------- User / GitHub ----------

export interface User {
  id: string;
  name: string;
  username?: string;
  email?: string;
  avatar_url?: string;
  github_login?: string;
  github_bound?: boolean;
  github_token_masked?: string;
  /** Legacy compatibility field. */
  pat_masked?: string;
  /** ISO creation time (OverviewPage hero renders formatDateTime(user.created_at)). */
  created_at?: string;
  /** Extension: role. */
  role?: 'owner' | 'user' | 'guest';
}

export interface GitHubAccount {
  id: string;
  username: string;
  pat_masked: string;
}

export interface StarsListResult {
  items: Array<{
    full_name: string;
    description: string;
    stars: number;
    language: string | null;
    html_url: string;
  }>;
  total: number;
}

export interface StarRepo {
  id?: string;
  full_name: string;
  owner: string;
  repo: string;
  description: string;
  stars: number;
  language: string | null;
  html_url: string;
  url?: string;
  avatar_url?: string;
  topics?: string[];
  fetched_at?: number;
  already_imported?: boolean;
}

// ---------- Project (legacy) → Repo (current) ----------

export interface Project {
  id: string;
  name: string;
  full_name: string;
  description: string;
  language: string | null;
  stars: number;
  category_id: string | null;
  category_ids?: string[];
  tag_ids?: string[];
  progress: 'none' | 'learning' | 'learned' | 'mastered';
  source: 'github' | 'gitee' | 'manual' | 'imported';
  status: 'importing' | 'ready' | 'failed';
  local_path?: string;
  readme?: string;
  /** Backend repo.category is a category-name string (a list_repos row field), not a
   *  Category object. */
  category?: string | null;
  notes_count?: number;
  added_ts: number;
  updated_ts: number;
  imported_at?: string;
  /** Repo-side tags are an array of string ids (backend repo.tags JSON array); display
   *  names are resolved through the Tag table from useTags() (ProjectTable.tagMap /
   *  ProjectInfoCard). */
  tags?: string[];
  relevance?: number;
  /** Legacy compatibility field. */
  project_id?: string;
  url?: string;
  html_url?: string;
  created_at?: number;
  updated_at?: number;
  cached?: boolean;
}

/** Project learning progress (legacy standalone export alias for Project['progress']). */
export type ProjectProgress = Project['progress'];

export interface ProjectListParams {
  search?: string;
  category_id?: string;
  language?: string;
  progress?: Project['progress'];
  tag_id?: string;
  sort_by?: 'name' | 'stars' | 'imported_at' | 'updated_at';
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface ProjectReadme {
  content: string;
  html_url?: string;
}

export interface ProjectStats {
  by_progress: Record<string, number>;
  by_category: Record<string, number>;
  by_language: Record<string, number>;
  total: number;
  cached?: number;
  fetched_at?: number;
}

export interface ProjectIndexProgress {
  project_id: string;
  status: 'idle' | 'indexing' | 'ready' | 'failed';
  files_indexed: number;
  total_files: number;
  updated_ts: number;
  error?: string;
}

export interface CreateProjectInput {
  url: string;
  name?: string;
  category_id?: string;
  progress?: Project['progress'];
  note?: string;
  /** Legacy fields kept during the project-to-resource transition. */
  full_name?: string;
  description?: string;
  language?: string | null;
  stars?: number;
}

export interface UpdateProjectInput {
  progress?: Project['progress'];
  category_id?: string | null;
  tag_ids?: string[];
  local_path?: string;
  readme?: string;
}

// ---------- Category / Tag ----------

export interface Category {
  id: string;
  name: string;
  count?: number;
  icon?: string;
  is_preset?: boolean;
  preset_id?: string;
  color?: string;
  sort_order?: number;
}

/** Tag object: an entry of the tag table returned by useTags(). FilterBar (t.id/t.name),
 *  ProjectTable tagMap, EditProjectModal and CategoryTagManager (t.id/t.name/t.count)
 *  all access it as an object. */
export interface Tag {
  id: string;
  name: string;
  count?: number;
}

export interface TagRef {
  id: string;
  name: string;
  count?: number;
}

export interface SetProjectTagsResult {
  project_id: string;
  tag_ids: string[];
}

// ---------- Import / indexing ----------

export interface ImportResult {
  queued: string[];
  failed: Array<{ url: string; reason: string }>;
}

export interface IndexStatus {
  status: 'idle' | 'running' | 'paused' | 'failed' | 'done';
  total: number;
  indexed: number;
  failed: number;
  updated_ts: number;
}

/** Import-assistant context (EmbedAgentChat importContext), constructed by
 *  ImportStarsDrawer/ImportUrlsModal with mode/available_repo_keys/
 *  selected_repo_keys/available_repos/imported_projects. */
export interface ImportAssistContext {
  mode: 'stars' | 'search' | 'urls';
  available_repo_keys?: string[];
  selected_repo_keys?: string[];
  available_repos?: Array<{
    key: string;
    language: string | null;
    stars: number;
    already_imported: boolean;
    description: string | null;
  }>;
  imported_projects?: Array<{
    name: string;
    language?: string | null;
    progress?: string;
    stars?: number;
    description?: string | null;
  }>;
}
