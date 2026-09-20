/**
 * @file agent.ts
 * @description Facade over the agent capability domain used by pages and UI.
 *
 * Capability names are centralized here so literals never leak into
 * components. All functions return the bridge payload directly; list-style
 * capabilities are normalized in this layer to arrays or stable shapes.
 *
 * Responsibilities:
 * - Wrap agent capabilities: subagents, personas, tools, memory/profile,
 *   plugins, user hooks, skills, MCP servers and the resource quota
 * - Normalize list-style payloads into plain arrays or stable shapes
 * - Keep capability name literals out of pages and components
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, ServiceError, unwrapDataField } from '@/bridge/client';

function asArray<T>(raw: T[] | { [k: string]: T[] | undefined }, key: string): T[] {
  if (Array.isArray(raw)) return raw;
  const nested = (raw as Record<string, T[] | undefined>)[key];
  return Array.isArray(nested) ? nested : [];
}

/** subagent (action=list): definitions plus running instances. */
export async function listSubagents(): Promise<{
  definitions: unknown[];
  running: unknown[];
}> {
  const raw = await callCapability<{
    definitions?: unknown[];
    running?: unknown[];
  }>('agent', 'subagent', { action: 'list' });
  return {
    definitions: raw.definitions ?? [],
    running: raw.running ?? [],
  };
}

/** todowrite (action=query): the agent's current plan (the per-session file
 *  the todowrite tool maintains; session-less work shares workspace/todo.json). */
export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'done';
}

export async function listTodos(
  session?: string
): Promise<{ items: TodoItem[]; done: number; total: number }> {
  const raw = await callCapability<{ items?: TodoItem[]; done?: number; total?: number }>(
    'agent',
    'todowrite',
    { action: 'query', session: session ?? '' }
  );
  return {
    items: Array.isArray(raw.items) ? raw.items : [],
    done: raw.done ?? 0,
    total: raw.total ?? 0,
  };
}

export async function listPersonas<T = unknown>(): Promise<T[]> {
  const raw = await callCapability<T[] | { personas: T[] }>('agent', 'list_personas', {});
  return asArray(raw, 'personas');
}

export async function listTools<T = unknown>(): Promise<T[]> {
  const raw = await callCapability<T[] | { tools: T[] }>('agent', 'tools', { action: 'list' });
  return asArray(raw, 'tools');
}

export function registerSubagent(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'subagent', { action: 'register', ...args });
}

export function deleteSubagent(name: string): Promise<{ deleted?: string }> {
  return callCapability('agent', 'subagent', { action: 'unregister', name });
}

/** describe_tool: full metadata for one tool roster entry (parameters schema included). */
export function describeTool<T = unknown>(name: string): Promise<T> {
  return callCapability<T>('agent', 'tools', { action: 'describe', name });
}

export function cancelRun(idOrName: string): Promise<{ cancelled?: string[] } | unknown> {
  return callCapability('agent', 'agent_instance', { action: 'cancel', id_or_name: idOrName });
}

export async function listResumableCheckpoints<T = unknown>(): Promise<T[]> {
  const raw = await callCapability<{ items?: T[] }>('agent', 'agent_instance', {
    action: 'checkpoints',
  });
  return raw.items ?? [];
}

export function resumeRun(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'agent_instance', { action: 'resume', ...args });
}

export function abandonResumableCheckpoint(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'agent_instance', { action: 'abandon', ...args });
}

export function answerQuestion(args: Record<string, unknown>): Promise<{ matched: boolean }> {
  return callCapability('agent', 'answer_question', args);
}

export function reportPageContext(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'report_page_context', args);
}

/** The aggregated memory capability: one action parameter (design §3). */
function memoryCap<T>(action: string, params: Record<string, unknown> = {}): Promise<T> {
  return callCapability<T>('agent', 'memory', { action, ...params });
}

export function getMemory<T = unknown>(): Promise<T> {
  return memoryCap<T>('query');
}

export function setProfile(key: string, value: unknown): Promise<unknown> {
  return memoryCap('remember', { key, value });
}

export function deleteProfile(key: string): Promise<unknown> {
  return memoryCap('forget', { key });
}

export function clearMemory(zone: string): Promise<unknown> {
  return memoryCap('clear', { zone });
}

export async function listPlugins<T = unknown>(): Promise<T[]> {
  const raw = await callCapability<{ items?: T[] }>('agent', 'extension', {
    kind: 'plugin',
    action: 'list',
  });
  return raw.items ?? [];
}

export function setPluginApproval(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'set_plugin_approval', args);
}

export function installPlugin(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'extension', { kind: 'plugin', action: 'install', ...args });
}

export function uninstallPlugin(name: string): Promise<unknown> {
  return callCapability('agent', 'extension', { kind: 'plugin', action: 'uninstall', name });
}

export async function listUserHooks<T = unknown>(): Promise<T[]> {
  const raw = await callCapability<{ items?: T[] }>('agent', 'extension', {
    kind: 'hook',
    action: 'list',
  });
  return raw.items ?? [];
}

export function reloadUserHooks<T = unknown>(): Promise<T> {
  return callCapability<T>('agent', 'extension', { kind: 'hook', action: 'reload' });
}

export function listSkills<T = unknown>(): Promise<T[]> {
  return callCapability<T[]>('agent', 'list_skills', {}).then((r) => (Array.isArray(r) ? r : []));
}

export function listMcpServers<T = unknown>(): Promise<T[]> {
  return callCapability<T[]>('agent', 'extension', { kind: 'mcp', action: 'list' }).then((r) =>
    Array.isArray(r) ? r : []
  );
}

export function addMcpServer(args: Record<string, unknown>): Promise<unknown> {
  return callCapability('agent', 'add_mcp_server', args);
}

export function previewMcpTools(id: string): Promise<unknown> {
  return callCapability('agent', 'extension', { kind: 'mcp', action: 'preview', id });
}

export function approveMcpTools(id: string, names: string[]): Promise<unknown> {
  return callCapability('agent', 'approve_mcp_tools', { id, names });
}

export function removeMcpServer(id: string): Promise<unknown> {
  return callCapability('agent', 'remove_mcp_server', { id });
}

export interface ResourceQuota {
  tokens_used_today: number;
  daily_tokens: number;
}

export function getResourceQuota(): Promise<ResourceQuota> {
  return callCapability<ResourceQuota>('agent', 'observe', { action: 'quota' }).then(
    unwrapDataField<ResourceQuota>
  );
}

// ---- Chat sessions & context (multi-session) --------------------------

/** One row of agent.session(action=list). */
export interface ChatSessionRow {
  session_id: string;
  title: string;
  persona?: string;
  status: string;
  active?: boolean;
  turns?: number | null;
  updated_at?: number | null;
  pinned?: boolean;
  archived?: boolean;
}

/** The aggregated session capability: one action parameter (design §3). */
function sessionCap<T>(action: string, params: Record<string, unknown> = {}): Promise<T> {
  return callCapability<T>('agent', 'session', { action, ...params });
}

export async function listSessions(): Promise<{
  sessions: ChatSessionRow[];
  active: string;
}> {
  const raw = await sessionCap<{
    sessions?: ChatSessionRow[];
    active?: string;
  }>('list');
  return { sessions: raw.sessions ?? [], active: raw.active ?? '' };
}

export function createSession(title = ''): Promise<{ session_id: string; title: string }> {
  return sessionCap('create', { title });
}

export function renameSession(sessionId: string, title: string): Promise<unknown> {
  return sessionCap('rename', { session_id: sessionId, title });
}

export function deleteSession(sessionId: string): Promise<unknown> {
  return sessionCap('delete', { session_id: sessionId });
}

export function setActiveSession(sessionId: string): Promise<unknown> {
  return sessionCap('set_active', { session_id: sessionId });
}

export function forkSession(
  sourceSessionId = '',
  title = '',
  keepMessages = 0
): Promise<{ session_id: string; forked_from?: string }> {
  return sessionCap('fork', {
    source_session_id: sourceSessionId,
    title,
    keep_messages: keepMessages,
  });
}

export function pinSession(sessionId: string, pinned = true): Promise<unknown> {
  return sessionCap('pin', { session_id: sessionId, pinned });
}

export function archiveSession(sessionId: string, archived = true): Promise<unknown> {
  return sessionCap('archive', { session_id: sessionId, archived });
}

/** User verdict on a finished agent turn, stored as memory (agent.rate_turn). */
export function rateTurn(score: number, comment = '', subject = ''): Promise<unknown> {
  return callCapability('agent', 'rate_turn', { score, comment, subject });
}

/** Context-window usage of one session (agent.context, action=status). */
export interface ContextStatus {
  window_tokens: number;
  max_output_tokens: number;
  usable_tokens: number;
  used_tokens: number;
  used_pct: number;
  auto_compact_at_pct: number;
  entries?: number;
  /** Extra usage_status breakdown fields (optional: absent in degraded shapes) */
  estimate_tokens?: number;
  reported_tokens?: number;
  memory_cards_tokens?: number;
  prefix_cache?: {
    turns?: number;
    warm_rounds?: number;
    cold_rounds?: number;
    unexplained_misses?: number;
    head_changes?: number;
    last_break?: number | null;
  };
}

export function getContextStatus(sessionId = ''): Promise<ContextStatus> {
  return callCapability<ContextStatus | { error: string }>('agent', 'context', {
    action: 'status',
    session_id: sessionId,
  }).then((raw) => {
    // Soft-failure shape: an unknown session answers {"error": "..."} with
    // HTTP 200 (not a ServiceError envelope). Reject so callers' catch paths
    // hit their null fallbacks instead of reading undefined fields as NaN.
    if (raw && typeof raw === 'object' && 'error' in raw) {
      throw new ServiceError('NOT_FOUND', String(raw.error));
    }
    return raw as ContextStatus;
  });
}

export function compactSession(sessionId = ''): Promise<Record<string, unknown>> {
  return callCapability('agent', 'context', { action: 'compact', session_id: sessionId });
}
