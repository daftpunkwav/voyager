/**
 * @file SettingsPanel
 * @description Renders the active section of the settings page.
 *
 * Responsibilities:
 * - Map a section id onto the panel that renders it
 * - Render exactly the active section
 *
 * Constraints:
 * - Only the active renderer is called, so a section's copy resolves through
 *   i18n at the moment it is shown, not for every section on every render.
 */

import type { ReactNode } from 'react';

import type { SettingsSection } from './sectionCatalog';
import {
  AgentLlmSection,
  AgentsSection,
  BehaviorSection,
  CommandsSection,
  ExecutionSection,
  McpSection,
  MemorySection,
  PluginsSection,
  SkillsSection,
  SubagentsSection,
  ToolPermsSection,
  ToolsSection,
} from './sections/AgentSections';
import { AppearanceSection, GeneralSection, LlmSection } from './sections/BasicSections';
import {
  AboutSection,
  ActivitySection,
  DataSection,
  DomainsSection,
  HealthSection,
  UsageSection,
} from './sections/SystemSections';

/** Renders one section of the page. */
type SectionRenderer = () => ReactNode;

const SECTION_RENDERERS: Record<SettingsSection, SectionRenderer> = {
  general: () => <GeneralSection />,
  appearance: () => <AppearanceSection />,
  llm: () => <LlmSection />,
  agents: () => <AgentsSection />,
  behavior: () => <BehaviorSection />,
  execution: () => <ExecutionSection />,
  memory: () => <MemorySection />,
  agentLlm: () => <AgentLlmSection />,
  subagents: () => <SubagentsSection />,
  plugins: () => <PluginsSection />,
  mcp: () => <McpSection />,
  skills: () => <SkillsSection />,
  commands: () => <CommandsSection />,
  tools: () => <ToolsSection />,
  toolPerms: () => <ToolPermsSection />,
  health: () => <HealthSection />,
  usage: () => <UsageSection />,
  activity: () => <ActivitySection />,
  data: () => <DataSection />,
  domains: () => <DomainsSection />,
  about: () => <AboutSection />,
};

interface SettingsPanelProps {
  /** The section to render. */
  section: SettingsSection;
}

export function SettingsPanel({ section }: SettingsPanelProps) {
  return <>{SECTION_RENDERERS[section]()}</>;
}
