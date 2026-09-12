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

import { PersonaGrid } from './PersonaGrid';
import { DefinitionGrid } from './DefinitionGrid';
import { SpawnForm } from './SpawnForm';
import { ToolCatalog } from './ToolCatalog';
import { ResumableList } from './ResumableList';
import { InstanceList } from './InstanceList';

export function TeamPage() {
  return (
    <div className="team-page page-scaffold">
      <div className="page-scaffold__body">
        <PersonaGrid />
        <DefinitionGrid />
        <SpawnForm />
        <ToolCatalog />
        <ResumableList />
        <InstanceList />
      </div>
    </div>
  );
}

export default TeamPage;
