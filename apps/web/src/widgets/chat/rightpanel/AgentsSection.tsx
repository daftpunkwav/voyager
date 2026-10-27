/**
 * @file AgentsSection
 * @description The panel's agents section: the resident teammate roster plus
 * the generic runs no roster agent owns, separated by a divider.
 *
 * Responsibilities:
 * - Split the polled instances into roster-owned and generic runs
 * - Render the resident roster and the generic run list
 * - Show the live run count as the section meta
 *
 * Constraints:
 * - Presentation only: the polled instances arrive through props, this
 *   section never polls or reads the store itself.
 */

import { useTranslation } from 'react-i18next';
import { SideSection } from '@/widgets/chat/rightpanel/SideSection';
import { AgentRoster } from '@/widgets/chat/rightpanel/AgentRoster';
import { GenericRunList } from '@/widgets/chat/rightpanel/GenericRunList';
import { type RunningInstance, residentRunRow } from '@/widgets/chat/rightpanel/runInstances';

export function AgentsSection({
  running,
  settled,
  now,
  onSelectRun,
}: {
  running: RunningInstance[];
  settled: RunningInstance[];
  now: number;
  onSelectRun: (run: RunningInstance | null) => void;
}) {
  const { t } = useTranslation('chat');
  // Generic (persona-less / non-roster) runs list under the roster divider;
  // a resident teammate's run is reflected in that teammate's own row.
  const genericRuns = [...running, ...settled].filter((r) => residentRunRow(r) === null);
  return (
    <SideSection
      title={t('chat:panel.agents')}
      meta={running.length > 0 ? running.length : undefined}
    >
      {/* Resident roster: every teammate (Lucien included) is always listed,
          one per line, with a live status readout; a run owned by a resident
          lights up that teammate's row instead of listing separately. The
          main conversational run never parks as settled — when the turn
          ends Lucien simply returns to idle. */}
      <AgentRoster running={running} settled={settled} now={now} onSelectRun={onSelectRun} />
      {genericRuns.length > 0 ? (
        <>
          <div className="chat-side__divider" aria-hidden />
          <GenericRunList runs={genericRuns} now={now} onSelectRun={onSelectRun} />
        </>
      ) : null}
    </SideSection>
  );
}
