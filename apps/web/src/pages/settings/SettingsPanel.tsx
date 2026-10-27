/**
 * @file SettingsPanel
 * @description Renders the active section of the settings page.
 *
 * Responsibilities:
 * - Hold the content of every section: which blocks a section shows
 * - Render exactly the active section, inside the section panel
 *
 * Constraints:
 * - The entries are elements, not render functions: a section is picked by
 *   its id, and nothing is invoked through the lookup.
 * - The heading and the card chrome come from the section panel, which
 *   resolves them from the section catalog.
 */

import type { ReactNode } from 'react';

import { AgentLlmOverridesPanel } from '@/components/settings/llm/AgentLlmOverridesPanel';
import { ArbiterBlock } from '@/components/settings/agent/ArbiterBlock';
import { AppPolicyBlock } from '@/components/settings/agent/AppPolicyBlock';
import { ConductBlock } from '@/components/settings/agent/ConductBlock';
import { DynamicSettingsGroup } from '@/components/settings/dynamic/DynamicSettingsGroup';
import { GuidelinesBlock } from '@/components/settings/agent/GuidelinesBlock';
import { LlmSettingsSection } from '@/components/settings/LlmSettingsSection';
import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';
import { McpBlock } from '@/components/settings/agent/McpBlock';
import { MemoryBlock } from '@/components/settings/agent/MemoryBlock';
import { MemoryRetentionBlock } from '@/components/settings/agent/MemoryRetentionBlock';
import { NetworkBlock } from '@/components/settings/agent/NetworkBlock';
import { PluginsBlock } from '@/components/settings/agent/PluginsBlock';
import { ReadRootsBlock } from '@/components/settings/agent/ReadRootsBlock';
import { RoundsBlock } from '@/components/settings/agent/RoundsBlock';
import { SkillsBlock } from '@/components/settings/agent/SkillsBlock';
import { StyleBlock } from '@/components/settings/agent/StyleBlock';
import { SubagentsSection as SubagentsBlock } from '@/components/settings/subagents/SubagentsSection';
import { TokenQuotaBlock } from '@/components/settings/agent/TokenQuotaBlock';
import { ToolPermissions } from '@/components/settings/tools/ToolPermissions';
import { ToolsCatalog } from '@/components/settings/tools/ToolsCatalog';
import { UserHooksBlock } from '@/components/settings/agent/UserHooksBlock';
import { WorkspaceBlock } from '@/components/settings/agent/WorkspaceBlock';
import { WriteRootsBlock } from '@/components/settings/agent/WriteRootsBlock';
import { PersonaGrid } from '@/components/team/PersonaGrid';
import { InstanceList } from '@/components/team/InstanceList';
import { ResumableList } from '@/components/team/ResumableList';

import type { SettingsSection } from './sectionCatalog';
import { SettingsSectionPanel } from './SettingsSectionPanel';
import { AppearanceSection, GeneralSection } from './sections/BasicSections';
import {
  AboutSection,
  ActivitySection,
  DataSection,
  HealthSection,
} from './sections/SystemSections';

const SECTION_CONTENT: Record<SettingsSection, ReactNode> = {
  general: <GeneralSection />,
  appearance: <AppearanceSection />,
  llm: (
    <>
      <LlmSettingsSection />
      <DynamicSettingsGroup modules={['llm']} titleKey="llm.dynamics" />
    </>
  ),
  agents: <PersonaGrid />,
  behavior: (
    <>
      <ArbiterBlock />
      <StyleBlock />
      <ConductBlock />
      <GuidelinesBlock />
      <DynamicSettingsGroup
        prefixes={['agent.outreach.', 'agent.triggers.', 'agent.direct_chat']}
        titleKey="behavior.dynamics"
      />
    </>
  ),
  execution: (
    <>
      <RoundsBlock />
      <TokenQuotaBlock />
      <NetworkBlock />
      <WorkspaceBlock />
      <ReadRootsBlock />
      <WriteRootsBlock />
      <AppPolicyBlock />
      <DynamicSettingsGroup
        prefixes={['agent.execution.', 'agent.context.', 'agent.retention.']}
        titleKey="execution.dynamics"
      />
    </>
  ),
  memory: (
    <>
      <MemoryBlock />
      <MemoryRetentionBlock />
      <DynamicSettingsGroup
        prefixes={[
          'agent.memory.distill_interval',
          'agent.memory.context_cards',
          'agent.memory.context_card_chars',
          'agent.memory.recall_facts',
          'agent.memory.recall_chars',
          'agent.memory.profile_chars',
          'agent.skills.organize_every',
        ]}
        titleKey="memory.dynamics"
      />
    </>
  ),
  agentLlm: (
    <>
      <AgentLlmOverridesPanel />
      <DynamicSettingsGroup
        prefixes={[
          'agent.llm.routing',
          'agent.llm.base_url',
          'agent.llm.api_key',
          'agent.llm.model',
          'agent.llm.timeout_s',
          'agent.pricing.',
        ]}
        titleKey="agentLlm.dynamics"
      />
    </>
  ),
  subagents: (
    <>
      <SubagentsBlock />
      <InstanceList />
      <ResumableList />
      <DynamicSettingsGroup prefixes={['agent.subagents.']} />
    </>
  ),
  plugins: <PluginsBlock />,
  mcp: (
    <>
      <McpBlock />
      <DynamicSettingsGroup
        prefixes={[
          'agent.mcp.wire_timeout_s',
          'agent.mcp.refresh_seconds',
          'agent.mcp.instructions',
        ]}
      />
    </>
  ),
  skills: <SkillsBlock />,
  commands: <UserHooksBlock />,
  tools: <ToolsCatalog />,
  toolPerms: <ToolPermissions />,
  health: <HealthSection />,
  usage: <LlmUsageDashboard />,
  activity: <ActivitySection />,
  data: <DataSection />,
  domains: (
    <>
      <DynamicSettingsGroup
        modules={['gateway', 'graph', 'sources', 'browser', 'code_exec', 'office']}
        titleKey="domains.services"
      />
      <DynamicSettingsGroup
        prefixes={[
          'notes.sort.',
          'notes.list.',
          'notes.editor.',
          'notes.trash.',
          'notes.history.',
          'notes.export.',
          'notes.assets.',
        ]}
        titleKey="domains.notes"
      />
      <DynamicSettingsGroup
        prefixes={['agent.observability.', 'agent.evaluation.']}
        titleKey="domains.observability"
      />
      <DynamicSettingsGroup prefixes={['host.domains.']} titleKey="domains.system" />
    </>
  ),
  about: <AboutSection />,
};

interface SettingsPanelProps {
  /** The section to render. */
  section: SettingsSection;
}

export function SettingsPanel({ section }: SettingsPanelProps) {
  return <SettingsSectionPanel section={section}>{SECTION_CONTENT[section]}</SettingsSectionPanel>;
}
