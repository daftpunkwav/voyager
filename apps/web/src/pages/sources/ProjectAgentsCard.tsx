/**
 * @file ProjectAgentsCard
 * @description Project detail sidebar card for AI learning assistants (expert persona grid; click to invoke).
 *
 * AgentDefinition comes from @/constants/agentCatalog (single source of truth,
 * not a domain type).
 *
 * Responsibilities:
 * - Render the expert persona grid with recommended and active highlights
 * - Raise agent invocation and the AI-tab navigation to the coordinator
 *   page
 */
import type { AgentId } from '@/api/types';
import { useTranslation } from 'react-i18next';
import type { AgentDefinition } from '@/constants/agentCatalog';
import { GLASS_OUTER } from '@/constants/glassTokens';

interface ProjectAgentsCardProps {
  /** Expert catalog for the detail page (DETAIL_AGENTS on the coordinator page, coordinator excluded) */
  agents: AgentDefinition[];
  recommendedAgent: AgentId;
  activeAgent: AgentId;
  /** Whether the detail page is currently on the AI tab (drives the card's is-active highlight) */
  active: boolean;
  noteGenerating: boolean;
  /** Invokes an expert (runAgent on the coordinator page) */
  onRunAgent: (agent: AgentId) => void;
}

/** AI learning assistant card: expert persona grid */
export function ProjectAgentsCard({
  agents,
  recommendedAgent,
  activeAgent,
  active,
  noteGenerating,
  onRunAgent,
}: ProjectAgentsCardProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={GLASS_OUTER}>
      <div className="card-header">
        <div className="card-title">{t('sources:agents.title')}</div>
        <span className="card-subtitle">{agents.length} agents</span>
      </div>
      <div className="pd-agent-grid">
        {agents.map((a) => (
          <button
            key={a.id}
            type="button"
            className={`pd-agent ${a.id === recommendedAgent ? 'recommended' : ''} ${activeAgent === a.id && active ? 'is-active' : ''}`}
            disabled={noteGenerating}
            onClick={() => void onRunAgent(a.id as AgentId)}
          >
            <div className="pd-agent-body">
              <div className="pd-agent-icon" style={{ background: a.color }}>
                {a.name[0]}
              </div>
              <div className="pd-agent-name">{a.name}</div>
              <div className="pd-agent-desc">{a.tagline}</div>
            </div>
            <span className="pd-agent-call">{t('sources:agents.call')}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
