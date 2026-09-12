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

/** Schema aggregation across every registered service. */
export function getSettings(): Promise<SettingSchemaItem[]> {
  return callCapability('settings', 'get_settings', {});
}
