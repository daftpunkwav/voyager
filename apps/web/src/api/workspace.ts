/**
 * @file workspace.ts
 * @description Workspace browsing (gateway read-only endpoints): directory
 * listing inside the workspace for the file tree, capped text preview, and a
 * machine-wide directory picker used to choose a new workspace root.
 */

export interface WorkspaceEntry {
  name: string;
  type: 'directory' | 'file';
  size?: number;
}

interface MaybeError {
  error?: { code: string; message: string };
}

/** Plain GET against the gateway (these endpoints are REST, not capabilities). */
async function callRest<T>(path: string): Promise<T & MaybeError> {
  const resp = await fetch(path);
  if (!resp.ok) {
    throw new Error(`workspace request failed (${resp.status})`);
  }
  return (await resp.json()) as T & MaybeError;
}

export async function listWorkspace(
  path = ''
): Promise<{ path: string; entries: WorkspaceEntry[] } & MaybeError> {
  return callRest(`/api/workspace/list?path=${encodeURIComponent(path)}`);
}

export async function readWorkspaceFile(
  path: string,
  limit = 200
): Promise<{ lines: string[]; truncated: boolean; total_bytes: number } & MaybeError> {
  return callRest(`/api/workspace/read?path=${encodeURIComponent(path)}&limit=${limit}`);
}

export interface PickResult {
  path: string;
  parent: string | null;
  home: string;
  entries: WorkspaceEntry[];
}

export async function pickDirectory(path = ''): Promise<PickResult & MaybeError> {
  return callRest(`/api/workspace/pick?path=${encodeURIComponent(path)}`);
}
