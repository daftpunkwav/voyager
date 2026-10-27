/**
 * @file sectionCatalog
 * @description Section catalog of the settings page: the section ids, the
 * grouped navigation entries and the ids a deep link may carry.
 *
 * Responsibilities:
 * - Own the section id union shared by the page, the navigation and the panel
 * - Own the grouped navigation catalog (basic / agent / system)
 *
 * Constraints:
 * - This module holds data only: no React, no UI components. The navigation
 *   renders the catalog, the panel dispatches on the ids.
 * - Labels resolve through the settings namespace at render time so the active
 *   language applies; icons are stroke glyphs keyed into SettingsIcons.
 */

import type { SettingsIcons } from '@/components/icons/SettingsIcons';
import { PRODUCT_NAME } from '@/brand';

/** A section of the settings page, addressable as ?section=<id>. */
export type SettingsSection =
  | 'general'
  | 'appearance'
  | 'llm'
  | 'agents'
  | 'behavior'
  | 'execution'
  | 'memory'
  | 'agentLlm'
  | 'subagents'
  | 'plugins'
  | 'mcp'
  | 'skills'
  | 'commands'
  | 'tools'
  | 'toolPerms'
  | 'health'
  | 'usage'
  | 'activity'
  | 'data'
  | 'domains'
  | 'about';

/** One entry of the grouped settings navigation. */
export interface SettingsNavItem {
  id: SettingsSection;
  icon: keyof typeof SettingsIcons;
}

/** A titled group of navigation entries. */
export interface SettingsNavGroup {
  labelKey: string;
  items: SettingsNavItem[];
}

/** The navigation catalog: basic, agent capabilities, data & system. */
export const NAV_GROUPS: SettingsNavGroup[] = [
  {
    labelKey: 'navGroup.basic',
    items: [
      { id: 'general', icon: 'general' },
      { id: 'appearance', icon: 'appearance' },
      { id: 'llm', icon: 'llm' },
    ],
  },
  {
    labelKey: 'navGroup.agent',
    items: [
      { id: 'agents', icon: 'agents' },
      { id: 'behavior', icon: 'behavior' },
      { id: 'execution', icon: 'execution' },
      { id: 'memory', icon: 'memory' },
      { id: 'agentLlm', icon: 'agentLlm' },
      { id: 'subagents', icon: 'subagents' },
      { id: 'plugins', icon: 'plugins' },
      { id: 'mcp', icon: 'mcp' },
      { id: 'skills', icon: 'skills' },
      { id: 'commands', icon: 'commands' },
      { id: 'tools', icon: 'tools' },
      { id: 'toolPerms', icon: 'tools' },
    ],
  },
  {
    labelKey: 'navGroup.system',
    items: [
      { id: 'health', icon: 'health' },
      { id: 'usage', icon: 'usage' },
      { id: 'activity', icon: 'activity' },
      { id: 'data', icon: 'data' },
      { id: 'domains', icon: 'domains' },
      { id: 'about', icon: 'about' },
    ],
  },
];

/** Every section id a deep link may carry. */
export const NAV_SECTIONS: ReadonlySet<string> = new Set(
  NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id))
);

/** The heading of a section: its key, the values it interpolates and the
 *  variant of the shell it renders in. */
export interface SettingsSectionMeta {
  /** The heading key, resolved through the settings namespace at render time. */
  titleKey: string;
  /** The interpolation values of the heading, if it takes any. */
  titleValues?: Record<string, string>;
  /** The embedded variant renders the section without the card chrome. */
  embedded?: boolean;
}

/** The heading and the shell variant of every section. */
export const SECTION_META: Record<SettingsSection, SettingsSectionMeta> = {
  general: { titleKey: 'general.title' },
  appearance: { titleKey: 'appearance.title' },
  llm: { titleKey: 'llm.title' },
  agents: { titleKey: 'agents.title' },
  behavior: { titleKey: 'behavior.title' },
  execution: { titleKey: 'execution.title' },
  memory: { titleKey: 'memory.title' },
  agentLlm: { titleKey: 'llm.overrides.title' },
  subagents: { titleKey: 'subagents.title' },
  plugins: { titleKey: 'plugins.title' },
  mcp: { titleKey: 'mcp.title' },
  skills: { titleKey: 'skills.title' },
  commands: { titleKey: 'commands.title' },
  tools: { titleKey: 'tools.title' },
  toolPerms: { titleKey: 'toolPerms.title' },
  health: { titleKey: 'health.title' },
  usage: { titleKey: 'usage.title', embedded: true },
  activity: { titleKey: 'activity.title', embedded: true },
  data: { titleKey: 'data.title' },
  domains: { titleKey: 'domains.title' },
  about: { titleKey: 'about.title', titleValues: { name: PRODUCT_NAME } },
};
