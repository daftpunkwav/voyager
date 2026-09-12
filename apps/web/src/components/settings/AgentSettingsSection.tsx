/**
 * @file AgentSettingsSection
 * @description Settings -> Agent shell that assembles the behavior blocks.
 *
 * Each block owns its own state, fetches its own data, and reports via its own toasts.
 *
 * Responsibilities:
 * - Assemble the behavior blocks into a single settings section
 * - Own no settings state itself: each block loads, saves and toasts on its own
 *
 * Blocks fetch through the capability bridge and api helpers, never via direct fetch.
 */

import { AppPolicyBlock } from './agent/AppPolicyBlock';
import { ArbiterBlock } from './agent/ArbiterBlock';
import { ConductBlock } from './agent/ConductBlock';
import { GuidelinesBlock } from './agent/GuidelinesBlock';
import { McpBlock } from './agent/McpBlock';
import { MemoryBlock } from './agent/MemoryBlock';
import { MemoryRetentionBlock } from './agent/MemoryRetentionBlock';
import { NetworkBlock } from './agent/NetworkBlock';
import { PluginsBlock } from './agent/PluginsBlock';
import { ReadRootsBlock } from './agent/ReadRootsBlock';
import { RoundsBlock } from './agent/RoundsBlock';
import { SkillsBlock } from './agent/SkillsBlock';
import { StyleBlock } from './agent/StyleBlock';
import { TokenQuotaBlock } from './agent/TokenQuotaBlock';
import { UserHooksBlock } from './agent/UserHooksBlock';
import { WorkspaceBlock } from './agent/WorkspaceBlock';
import { WriteRootsBlock } from './agent/WriteRootsBlock';
import { useTranslation } from 'react-i18next';

/** Settings -> Agent: blocks grouped into four labeled categories so the 17
 *  knobs scan quickly; each block still owns its own state and toasts. */
export function AgentSettingsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>Agent</h2>
      <p className="section-desc">{t('agent.desc')}</p>

      <h3 className="settings-group-title">{t('agentGroup.behavior')}</h3>
      <ConductBlock />
      <StyleBlock />
      <GuidelinesBlock />

      <h3 className="settings-group-title">{t('agentGroup.runtime')}</h3>
      <RoundsBlock />
      <ArbiterBlock />
      <TokenQuotaBlock />
      <NetworkBlock />
      <WorkspaceBlock />
      <ReadRootsBlock />
      <WriteRootsBlock />

      <h3 className="settings-group-title">{t('agentGroup.automation')}</h3>
      <SkillsBlock />
      <UserHooksBlock />
      <PluginsBlock />
      <McpBlock />

      <h3 className="settings-group-title">{t('agentGroup.memoryPolicy')}</h3>
      <MemoryBlock />
      <MemoryRetentionBlock />
      <AppPolicyBlock />
    </section>
  );
}
