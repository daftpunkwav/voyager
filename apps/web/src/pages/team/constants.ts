/**
 * @file constants
 * @description Shared constants for the team-page spawn form.
 *
 * Option labels are display copy: they live in the team namespace
 * (team:mode.* / team:network.*) as flat keys and are resolved with t() at the
 * consumption site; `value` entries are backend enum values and stay untranslated.
 *
 * Responsibilities:
 * - Define the spawn-form constants: name regex, execution-mode and
 *   network-tier options (values match the backend enums)
 * - Resolve a value to its localized label, unknown values as-is
 */

import type { TFunction } from 'i18next';

/** Same name regex as the backend SubagentDef (agent/subagent/registry.py); validated client-side first. */
export const NAME_RE = /^[a-z][a-z0-9_]*$/;

/** Seven execution modes (agent/subagent/modes.py); submitted values are backend enum values. */
export const MODE_OPTIONS: { value: string; labelKey: string }[] = [
  { value: 'react', labelKey: 'team:mode.react' },
  { value: 'plan_execute', labelKey: 'team:mode.plan_execute' },
  { value: 'cot', labelKey: 'team:mode.cot' },
  { value: 'tot', labelKey: 'team:mode.tot' },
  { value: 'got', labelKey: 'team:mode.got' },
  { value: 'reflexion', labelKey: 'team:mode.reflexion' },
  { value: 'direct', labelKey: 'team:mode.direct' },
];

/** Display label for a mode value; unknown values render as-is (same fallback as the former MODE_LABELS map). */
export function modeLabel(t: TFunction, value: string): string {
  const hit = MODE_OPTIONS.find((o) => o.value === value);
  return hit ? t(hit.labelKey) : value;
}

/** Network tiers: '' = follow global setting; tier values match backend agent.network.mode. */
export const NETWORK_OPTIONS: { value: string; labelKey: string }[] = [
  { value: '', labelKey: 'team:option.followGlobal' },
  { value: 'off', labelKey: 'team:network.off' },
  { value: 'whitelist', labelKey: 'team:network.whitelist' },
  { value: 'all', labelKey: 'team:network.all' },
];

/** Display label for a network tier; unknown values render as-is (same fallback as the former NETWORK_LABELS map). */
export function networkLabel(t: TFunction, value: string): string {
  const hit = NETWORK_OPTIONS.find((o) => o.value === value);
  return hit ? t(hit.labelKey) : value;
}
