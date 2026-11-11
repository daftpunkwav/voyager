/**
 * @file sectionCatalog
 * @description Section catalog of the settings page: the section ids, the
 * metadata each section carries and the grouped navigation the rail renders.
 *
 * Responsibilities:
 * - Own the section id union shared by the page, the navigation and the panel
 * - Own the metadata of every section (group, icon, heading)
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

/** The navigation group a section is listed in. */
export type SettingsSectionGroup = 'basic' | 'agent' | 'system';

/** What the page needs to know about a section. */
export interface SettingsSectionMeta {
  /** The navigation group the section is listed in. */
  group: SettingsSectionGroup;
  /** The icon of the navigation entry. */
  icon: keyof typeof SettingsIcons;
  /** The heading key of the section, resolved through the settings namespace. */
  titleKey: string;
  /** The interpolation values of the heading, if it takes any. */
  titleValues?: Record<string, string>;
  /** The embedded variant renders the section without the card chrome. */
  embedded?: boolean;
}

/** The sections and their metadata, in the order the rail lists them. */
export const SECTIONS: Record<SettingsSection, SettingsSectionMeta> = {
  general: { group: 'basic', icon: 'general', titleKey: 'general.title' },
  appearance: { group: 'basic', icon: 'appearance', titleKey: 'appearance.title' },
  llm: { group: 'basic', icon: 'llm', titleKey: 'llm.title' },
  agents: { group: 'agent', icon: 'agents', titleKey: 'agents.title' },
  behavior: { group: 'agent', icon: 'behavior', titleKey: 'behavior.title' },
  execution: { group: 'agent', icon: 'execution', titleKey: 'execution.title' },
  memory: { group: 'agent', icon: 'memory', titleKey: 'memory.title' },
  agentLlm: { group: 'agent', icon: 'agentLlm', titleKey: 'llm.overrides.title' },
  subagents: { group: 'agent', icon: 'subagents', titleKey: 'subagents.title' },
  plugins: { group: 'agent', icon: 'plugins', titleKey: 'plugins.title' },
  mcp: { group: 'agent', icon: 'mcp', titleKey: 'mcp.title' },
  skills: { group: 'agent', icon: 'skills', titleKey: 'skills.title' },
  commands: { group: 'agent', icon: 'commands', titleKey: 'commands.title' },
  tools: { group: 'agent', icon: 'tools', titleKey: 'tools.title' },
  toolPerms: { group: 'agent', icon: 'tools', titleKey: 'toolPerms.title' },
  health: { group: 'system', icon: 'health', titleKey: 'health.title' },
  usage: { group: 'system', icon: 'usage', titleKey: 'usage.title', embedded: true },
  activity: { group: 'system', icon: 'activity', titleKey: 'activity.title', embedded: true },
  data: { group: 'system', icon: 'data', titleKey: 'data.title' },
  domains: { group: 'system', icon: 'domains', titleKey: 'domains.title' },
  about: {
    group: 'system',
    icon: 'about',
    titleKey: 'about.title',
    titleValues: { name: PRODUCT_NAME },
  },
};

/** The section ids, in the order the rail lists them. */
export const SECTION_IDS: SettingsSection[] = Object.keys(SECTIONS).filter(
  (id): id is SettingsSection => id in SECTIONS
);

/** The navigation groups, in the order they appear in the rail. */
const NAV_GROUP_LABELS: { labelKey: string; group: SettingsSectionGroup }[] = [
  { labelKey: 'navGroup.basic', group: 'basic' },
  { labelKey: 'navGroup.agent', group: 'agent' },
  { labelKey: 'navGroup.system', group: 'system' },
];

/** A titled group of navigation entries. */
export interface SettingsNavGroup {
  labelKey: string;
  items: SettingsSection[];
}

/** The grouped navigation catalog. */
export const NAV_GROUPS: SettingsNavGroup[] = NAV_GROUP_LABELS.map(({ labelKey, group }) => ({
  labelKey,
  items: SECTION_IDS.filter((id) => SECTIONS[id].group === group),
}));

/** Every section id a deep link may carry. */
export const NAV_SECTIONS: ReadonlySet<string> = new Set(SECTION_IDS);
