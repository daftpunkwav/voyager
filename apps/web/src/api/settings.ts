/**
 * @file settings.ts
 * @description Settings domain (settings service).
 *
 * get_settings returns the schema list used for gating and dynamic groups;
 * business pages read/write individual keys via get_setting / set_setting and
 * appearance via get_theme / set_theme (see hooks/useTheme, shell/themeBridge,
 * hooks/useLocale, shell/localeBridge). Payloads are returned directly,
 * without a {data} envelope.
 */

import { callCapability } from '@/bridge/client';
import type { SettingSchemaItem } from '@/api/types';

/**
 * Settings keys that components read/write directly via get_setting /
 * set_setting (the sanctioned callCapability exception documented in
 * api/llm.ts). Values must match the backend SettingDef registries.
 */
export const LLM_PROVIDER_KEY = 'llm.default_provider';
export const LLM_MODEL_KEY = 'llm.default_model';
export const LLM_REASONING_EFFORT_KEY = 'llm.reasoning_effort';

/** Schema aggregation across every registered service. */
export function getSettings(): Promise<SettingSchemaItem[]> {
  return callCapability('settings', 'get_settings', {});
}
