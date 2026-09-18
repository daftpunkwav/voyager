/**
 * @file toolGroups
 * @description Categorization for the agent tool roster: bridge tools group by
 * their domain prefix (notes__* -> notes), internal tools by dimension
 * (fs/shell/network/...). Consumed by the subagent tool picker and the
 * settings tool catalog so both share one grouping.
 */

import type { ToolItem } from './types';

export interface ToolGroup {
  /** Stable group key (domain prefix or dimension value); label resolves
   *  through team:toolGroup.<key> at the consumption site. */
  key: string;
  tools: ToolItem[];
}

/** Preferred group order: internal hands first, then domains, then the rest alphabetically. */
const GROUP_ORDER = [
  'fs',
  'shell',
  'network',
  'app',
  'skill',
  'plan',
  'none',
  'notes',
  'sources',
  'graph',
  'office',
  'llm',
  'settings',
  'browser',
  'code_exec',
  'mcp',
];

/** Domain prefix of a bridge tool name ("notes__create_note" -> "notes"); null for internal tools. */
export function toolDomain(name: string): string | null {
  const idx = name.indexOf('__');
  return idx > 0 ? name.slice(0, idx) : null;
}

/** Group key for one tool: domain prefix wins over dimension. */
export function toolGroupKey(tool: ToolItem): string {
  return toolDomain(tool.name) ?? (tool.dimension || 'other');
}

/** Split the roster into ordered groups; tools keep their roster order inside a group. */
export function groupTools(tools: ToolItem[]): { key: string; tools: ToolItem[] }[] {
  const byKey = new Map<string, ToolItem[]>();
  for (const tool of tools) {
    const key = toolGroupKey(tool);
    const bucket = byKey.get(key);
    if (bucket) bucket.push(tool);
    else byKey.set(key, [tool]);
  }
  return [...byKey.keys()]
    .sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a);
      const ib = GROUP_ORDER.indexOf(b);
      return (
        (ia === -1 ? GROUP_ORDER.length : ia) - (ib === -1 ? GROUP_ORDER.length : ib) ||
        a.localeCompare(b)
      );
    })
    .map((key) => ({ key, tools: byKey.get(key) ?? [] }));
}

/** Localized label for a group key; unknown keys render as-is (i18next returns the key itself when missing). */
export function toolGroupLabel(t: (key: string) => string, key: string): string {
  const label = t(`team:toolGroup.${key}`);
  return label === `toolGroup.${key}` ? key : label;
}
