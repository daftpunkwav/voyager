/**
 * @file AgentSections
 * @description The agent group of the settings page: the sections that
 * compose the agent blocks (personas, behavior, execution, memory, model
 * overrides, subagents, plugins, MCP, skills, commands and tools).
 *
 * Responsibilities:
 * - Compose the existing agent blocks into the section panels
 * - Attach the schema-driven groups that belong to the section
 *
 * Constraints:
 * - Every block owns its own state and its own write path; this module only
 *   places them and titles the panel.
 */

import { useTranslation } from 'react-i18next';

import { AgentLlmOverridesPanel } from '@/components/settings/llm/AgentLlmOverridesPanel';
import { ArbiterBlock } from '@/components/settings/agent/ArbiterBlock';
import { AppPolicyBlock } from '@/components/settings/agent/AppPolicyBlock';
import { ConductBlock } from '@/components/settings/agent/ConductBlock';
import { DynamicSettingsGroup } from '@/components/settings/dynamic/DynamicSettingsGroup';
import { GuidelinesBlock } from '@/components/settings/agent/GuidelinesBlock';
import { McpBlock } from '@/components/settings/agent/McpBlock';
import { MemoryBlock } from '@/components/settings/agent/MemoryBlock';
import { MemoryRetentionBlock } from '@/components/settings/agent/MemoryRetentionBlock';
import { NetworkBlock } from '@/components/settings/agent/NetworkBlock';
import { PluginsBlock } from '@/components/settings/agent/PluginsBlock';
import { ReadRootsBlock } from '@/components/settings/agent/ReadRootsBlock';
import { RoundsBlock } from '@/components/settings/agent/RoundsBlock';
import { SkillsBlock } from '@/components/settings/agent/SkillsBlock';
import { StyleBlock } from '@/components/settings/agent/StyleBlock';
// The block is named after its own component; the alias keeps it aligned with
// the sibling blocks and frees the section-panel name below.
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

/** The personas of the agent. */
export function AgentsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('agents.title')}</h2>
      <PersonaGrid />
    </section>
  );
}

/** The conduct rules: arbitration, style, conduct and the guidelines. */
export function BehaviorSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('behavior.title')}</h2>
      <ArbiterBlock />
      <StyleBlock />
      <ConductBlock />
      <GuidelinesBlock />
      <DynamicSettingsGroup
        prefixes={['agent.outreach.', 'agent.triggers.', 'agent.direct_chat']}
        titleKey="behavior.dynamics"
      />
    </section>
  );
}

/** The execution limits: rounds, quota, network, workspace and filesystem roots. */
export function ExecutionSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('execution.title')}</h2>
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
    </section>
  );
}

/** The agent memory: the memory block and the retention policy. */
export function MemorySection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('memory.title')}</h2>
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
    </section>
  );
}

/** The per-agent model overrides. */
export function AgentLlmSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('llm.overrides.title')}</h2>
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
    </section>
  );
}

/** The subagents and their instances. */
export function SubagentsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('subagents.title')}</h2>
      <SubagentsBlock />
      <InstanceList />
      <ResumableList />
      <DynamicSettingsGroup prefixes={['agent.subagents.']} />
    </section>
  );
}

/** The installed plugins. */
export function PluginsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('plugins.title')}</h2>
      <PluginsBlock />
    </section>
  );
}

/** The configured MCP servers. */
export function McpSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('mcp.title')}</h2>
      <McpBlock />
      <DynamicSettingsGroup
        prefixes={[
          'agent.mcp.wire_timeout_s',
          'agent.mcp.refresh_seconds',
          'agent.mcp.instructions',
        ]}
      />
    </section>
  );
}

/** The agent skills. */
export function SkillsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('skills.title')}</h2>
      <SkillsBlock />
    </section>
  );
}

/** The user hooks. */
export function CommandsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('commands.title')}</h2>
      <UserHooksBlock />
    </section>
  );
}

/** The tool catalog. */
export function ToolsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('tools.title')}</h2>
      <ToolsCatalog />
    </section>
  );
}

/** The per-tool permissions. */
export function ToolPermsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('toolPerms.title')}</h2>
      <ToolPermissions />
    </section>
  );
}
