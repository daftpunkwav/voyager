/**
 * @file RightPanel
 * @description Chat page side panel in three collapsible sections — plan,
 * agents, deliverables — mirroring a mainstream agent UI's progress sidebar.
 *
 * Data sources:
 * - Plan: agent.todowrite (action=query) polled every 5s for the open session (the same
 *   per-session list the LLM's todo_write maintains) with a done/total counter
 * - Agents: agent.list_subagents polled every 5s (no lifecycle SSE exists),
 *   filtered to the open session. A permanent roster row per teammate (Lucien
 *   included) carries that teammate's live status — idle / chatting / working
 *   with elapsed time and goal — and opens the run's execution view on click;
 *   generic unnamed runs list below the roster behind a divider (interrupt
 *   lives inside the view)
 * - Deliverables: note artifacts from chatStore (note.created) plus the live
 *   task.* progress cards (rendered by TaskCards, passed in as children);
 *   the section stays visible with an empty hint when there is nothing to show
 *
 * The panel itself only wires the three sections together; the section bodies
 * live in ./rightpanel, the polling behind them in ./rightpanel/usePanelData.
 */

import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { SubagentRunDialog } from '@/widgets/chat/SubagentRunDialog';
import { useChatStore } from '@/stores/chatStore';
import { PlanSection } from '@/widgets/chat/rightpanel/PlanSection';
import { AgentsSection } from '@/widgets/chat/rightpanel/AgentsSection';
import { DeliverablesSection } from '@/widgets/chat/rightpanel/DeliverablesSection';
import { usePlanTodos, useRunningAgents } from '@/widgets/chat/rightpanel/usePanelData';

export function RightPanel({ taskCards }: { taskCards: ReactNode }) {
  const { t } = useTranslation('chat');
  const artifacts = useChatStore((s) => s.artifacts);
  const cardCount = useChatStore((s) => s.cardOrder.length);
  const plan = usePlanTodos();
  const runs = useRunningAgents();

  return (
    <aside className="chat-side" aria-label={t('chat:panel.aria')}>
      <PlanSection todos={plan.todos} done={plan.done} total={plan.total} />
      <AgentsSection
        running={runs.running}
        settled={runs.settled}
        now={runs.now}
        onSelectRun={runs.selectRun}
      />
      <DeliverablesSection artifacts={artifacts} cardCount={cardCount} taskCards={taskCards} />
      <SubagentRunDialog
        instance={runs.runView}
        open={runs.runView !== null}
        onClose={runs.closeRun}
      />
    </aside>
  );
}
