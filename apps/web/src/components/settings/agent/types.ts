/**
 * @file types
 * @description Small shared types for the Agent settings blocks.
 *
 * Intentionally minimal — do not grow this into a giant types file.
 */

export interface SettingItem<T = string> {
  value?: T;
  default?: T;
}

export interface ProfileItem {
  key: string;
  value: unknown;
}

export interface EpisodicEntry {
  id: number;
  ts: number;
  kind: string;
  summary: string;
}

export interface SemanticFact {
  id: number;
  ts: number;
  subject: string;
  relation: string;
  object: string;
}

export interface MemorySnapshot {
  profile: { summary: string; items: ProfileItem[] };
  episodic: { recent: EpisodicEntry[]; shown: number };
  semantic: { recent: SemanticFact[]; shown: number };
  working: { size: number };
  retention_days: number;
  purged_episodic: number;
}

export type MemoryZone = 'profile' | 'episodic' | 'semantic' | 'working' | 'all';

export interface SkillItem {
  name: string;
  description: string;
}

export interface McpToolPreview {
  name: string;
  description: string;
}

export interface McpServerState {
  id: string;
  name: string;
  kind: 'stdio' | 'url';
  command: string;
  args: string[];
  url: string;
  approval: 'package' | 'item';
  approved: string[];
  enabled: boolean;
  connected: boolean;
  error: string;
  preview: McpToolPreview[];
  mounted: string[];
}

export interface McpAddResult {
  ok: boolean;
  id: string;
  connected: boolean;
  error: string;
  preview: McpToolPreview[];
}

export interface McpApproveResult {
  ok: boolean;
  approved: string[];
  mounted: string[];
}

export interface McpFormDraft {
  id: string;
  name: string;
  kind: 'stdio' | 'url';
  command: string;
  argsDraft: string;
  url: string;
  approval: 'package' | 'item';
}

export interface PluginPermissions {
  scopes: string[];
  network: string;
  fs: string;
}

/** Per-item detail entry from list_plugins */
export interface PluginSkillDetail {
  name: string;
  approved: boolean;
}

export interface PluginHookDetail {
  path: string; // Relative to the plugin directory; used for per-item approval/mounting
  on: string;
  enabled: boolean;
  approved: boolean;
}

export interface PluginMcpDetail {
  id: string;
  approved: boolean; // Whether the plugin has this server checked
  registered: boolean; // Whether it is already registered under external MCP (pending approval)
  tools_approved: string[]; // Already-approved tools stored in existing MCP (read-only; empty = unapproved tools)
}

export interface PluginItem {
  name: string;
  version: string;
  description: string;
  approved: boolean;
  granularity: '' | 'bundle' | 'item'; // Mount granularity when approved
  permissions: PluginPermissions;
  contains: { skills: number; hooks: number; mcp: boolean };
  skills: PluginSkillDetail[];
  hooks: PluginHookDetail[];
  mcp: PluginMcpDetail[];
  path: string;
}

export interface PluginApproveResult {
  name: string;
  approved: boolean;
  loaded: { skills: string[]; hooks: number; mcp_registered: number; mcp_skipped: boolean };
  granularity?: 'bundle' | 'item';
  skipped?: { skills: string[]; hooks: string[]; mcp: string[] };
  /** External MCP server ids reclaimed per safety rules when approval is revoked or changed */
  mcp_reclaimed?: string[];
  /** External MCP servers not reclaimed, with reasons (tools already approved / still used by another plugin / config mismatch, etc.) */
  mcp_reclaim_skipped?: { id: string; reason: string }[];
}

/** install_plugin response: installed successfully but not yet approved; approval still goes through set_plugin_approval */
export interface PluginInstallResult {
  name: string;
  version: string;
  path: string;
  permissions: PluginPermissions;
  contains_summary: { skills: number; hooks: number; mcp: boolean };
}

/** Per-item entry from list_user_hooks: declarative hook JSON files under workspace/hooks */
export interface UserHookItem {
  path: string;
  on: string;
  enabled: boolean;
  description: string;
  loaded: boolean;
}

/** reload_user_hooks response: hot load/unload results that take effect without a restart */
export interface UserHooksReloadResult {
  loaded: number;
  event_patterns: string[];
  skipped?: { path: string; reason: string }[];
}
