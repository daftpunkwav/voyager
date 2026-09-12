/**
 * @file types/settings.ts
 * @description Settings domain types matching the real backend contract.
 *
 * `get_settings` returns the flat schema list across services (verified
 * against the settings service); single-key reads/writes go through
 * get_setting / set_setting, and appearance values (theme / font_scale /
 * code_font) through get_theme / set_theme. There is no nested settings blob.
 */

/** One schema row as returned by settings.get_settings / get_setting. */
export interface SettingSchemaItem {
  key: string;
  module: string;
  /** Serialized SettingType discriminator (e.g. "str" | "int" | "float" | "bool" | "choice" | "json"). */
  type: string;
  description: string;
  secret: boolean;
  choices: string[];
  min: number | null;
  max: number | null;
  /** Whether a user value is stored (secrets only ever expose this, never the value). */
  has_value: boolean;
  default?: unknown;
  /** Current value; absent for secret items. */
  value?: unknown;
}
