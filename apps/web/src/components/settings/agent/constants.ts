/**
 * @file constants
 * @description Setting keys, limits, and option presets shared by the Agent settings blocks.
 *
 * Ranges mirror the backend SettingDef entries; option values must match the
 * backend enums exactly.
 */

import { AGENT_CATALOG } from '@/constants/agentCatalog';

export const CONDUCT_MAX = 4000;
export const GUIDELINE_MAX = 2000;

/** Global conduct rules (agent.conduct): user-written global rules injected into every conversation's system prompt */
export const CONDUCT_KEY = 'agent.conduct';
/** Per-agent conduct rules (agent.guidelines): { <persona struct id>: text }, layered on top of the global rules */
export const GUIDELINES_KEY = 'agent.guidelines';

/** Global speaking-style presets (agent.style, common values for the free-form string; layered over each persona's temperament)
 *  These are VALUES persisted to the backend (backend default "热心" aligns with the first preset),
 *  so they stay untranslated data, not display copy. */
export const STYLE_PRESETS = ['热心', '毒舌', '严谨', '简洁', '幽默', '专业'];
export const STYLE_KEY = 'agent.style';

/** Episodic memory retention days (agent.memory.retention_days; range matches SettingDef) */
export const RETENTION_KEY = 'agent.memory.retention_days';
export const RETENTION_MAX = 3650;

/** Conversation round limits (agent.rounds.*; range matches SettingDef) */
export const ROUNDS_MAX_KEY = 'agent.rounds.max';
export const ROUNDS_TOOL_KEY = 'agent.rounds.tool_max';
export const ROUNDS_RE_MAX = 200;
export const ROUNDS_TOOL_MAX = 500;

/** Daily token quota (agent.resource.daily_tokens): cap on the day's input+output combined; 0 = unlimited */
export const DAILY_TOKENS_KEY = 'agent.resource.daily_tokens';
export const DAILY_TOKENS_MAX = 10_000_000;

/** Network permissions (agent.network.*; tier values match the backend enum; labels resolve through settings:network.mode.*) */
export const NETWORK_MODE_KEY = 'agent.network.mode';
export const NETWORK_DOMAINS_KEY = 'agent.network.domains';
export const NETWORK_MODE_OPTIONS: { value: string; labelKey: string }[] = [
  { value: 'off', labelKey: 'settings:network.mode.off' },
  { value: 'whitelist', labelKey: 'settings:network.mode.whitelist' },
  { value: 'all', labelKey: 'settings:network.mode.all' },
];

// WORKDIR_KEY (agent.workspace.dir) lives in api/workspace.ts: the workspace
// domain owns the key, and widgets/chat imports it from there.

/** Additional read-only roots (agent.fs.read_roots): absolute path list; reads allowed, writes/deletes still limited to the working directory */
export const READ_ROOTS_KEY = 'agent.fs.read_roots';

/** Additional read-write roots (agent.fs.write_roots): absolute path list; reads at L0, writes/deletes require L2 confirmation, workspace still takes precedence */
export const WRITE_ROOTS_KEY = 'agent.fs.write_roots';

/** In-app capability allowlist (agent.app.*): user-editable only; hot-read and affects bridge tools */
export const APP_ALLOWED_KEY = 'agent.app.allowed';
export const APP_DENIED_KEY = 'agent.app.denied';

/** Memory-zone display keys (settings:memory.zone.*); components translate via t() */
export const ZONE_LABEL_KEYS: Record<
  'profile' | 'episodic' | 'semantic' | 'working' | 'all',
  string
> = {
  profile: 'settings:memory.zone.profile',
  episodic: 'settings:memory.zone.episodic',
  semantic: 'settings:memory.zone.semantic',
  working: 'settings:memory.zone.working',
  all: 'settings:memory.zone.all',
};

/** Zone-clear confirmation keys (settings:memory.confirm.*): copy makes explicit that the conversation timeline/notes/projects are kept */
export const ZONE_CONFIRM_KEYS: Record<'all' | 'profile' | 'episodic' | 'semantic', string> = {
  all: 'settings:memory.confirm.all',
  profile: 'settings:memory.confirm.profile',
  episodic: 'settings:memory.confirm.episodic',
  semantic: 'settings:memory.confirm.semantic',
};

export const EMPTY_MCP_FORM = {
  id: '',
  name: '',
  kind: 'stdio' as const,
  command: '',
  argsDraft: '',
  url: '',
  approval: 'package' as const,
};

/** Converts a get_setting value into a numeric input draft; non-numeric values (mock/anomalies) fall back to an empty string so NaN never lands in the draft */
export const numericDraft = (item: { value?: number; default?: number }) => {
  const n = Number(item.value ?? item.default);
  return Number.isFinite(n) ? String(n) : '';
};

/** Episodic timestamps are unix seconds; convert to local time for display */
export const fmtTs = (ts: number) => new Date(ts * 1000).toLocaleString();

/** Non-string profile values (numbers/objects) are shown as JSON to avoid "[object Object]" */
export const fmtValue = (value: unknown) =>
  typeof value === 'string' ? value : (JSON.stringify(value) ?? '');

export const DEFAULT_AGENT_ID = AGENT_CATALOG[0]?.id ?? 'orchestrator';
