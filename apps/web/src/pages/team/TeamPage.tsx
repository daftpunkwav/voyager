/**
 * @file TeamPage
 * @description Agent and subagent management page built on agent.list_subagents / list_personas / list_tools.
 *
 * Pure composition shell: renders six sections in business order. Each section
 * loads its own data, owns its own state, and reports its own toasts.
 *
 * Responsibilities:
 * - Compose the six team sections in business order without owning state
 *   or data
 */

import { PersonaGrid } from '@/components/team/PersonaGrid';
import { DefinitionGrid } from '@/components/team/DefinitionGrid';
import { SpawnForm } from '@/components/team/SpawnForm';
import { ToolsCatalog } from '@/components/settings/tools/ToolsCatalog';
import { ResumableList } from '@/components/team/ResumableList';
import { InstanceList } from '@/components/team/InstanceList';

export function TeamPage() {
  return (
    <div className="team-page page-scaffold">
      <div className="page-scaffold__body">
        <PersonaGrid />
        <DefinitionGrid />
        <SpawnForm />
        <ToolsCatalog />
        <ResumableList />
        <InstanceList />
      </div>
    </div>
  );
}

export default TeamPage;
