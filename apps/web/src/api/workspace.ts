/**
 * @file workspace.ts
 * @description Workspace browsing (gateway read-only endpoints): directory
 * listing inside the workspace for the file tree, capped text preview, a
 * machine-wide directory picker used to choose a new workspace root, and
 * the hot-switch endpoint that rebuilds the agent around the new root
 * without restarting the service.
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

export interface SwitchResult {
  workspace: string;
  previous?: string;
  note?: string;
}

/** Hot-switch the agent workspace: validates, rebuilds the agent around the
 *  new root, persists agent.workspace.dir and rebinds workspace routes.
 *  Throws the backend message on failure (validation / rebuild errors). */
export async function switchWorkspace(dir: string): Promise<SwitchResult> {
  const resp = await fetch('/api/workspace/switch', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ dir }),
  });
  const data = (await resp.json().catch(() => ({}))) as SwitchResult & MaybeError;
  if (!resp.ok || data.error) {
    throw new Error(data.error?.message ?? `workspace switch failed (${resp.status})`);
  }
  return data;
}
