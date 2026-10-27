/**
 * @file AgentRoster
 * @description The resident teammate roster of the panel's agents section:
 * one permanent row per catalog agent (Lucien included) carrying that
 * teammate's live status, elapsed task runtime and goal.
 *
 * Responsibilities:
 * - Map every catalog agent onto its live or parked run
 * - Render the row's status readout (chatting / working / settled / idle)
 * - Open the run's execution view when a row is clicked
 *
 * Constraints:
 * - Presentation only: the polled instances arrive through props, this
 *   component never polls or reads the store itself.
 */

import { useTranslation } from 'react-i18next';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { personaDisplayName } from '@/constants/personas';
import { AgentCharacterHead } from '@/components/agent/avatars/AgentCharacterHead';
import { formatDurationSec } from '@/utils/trajectory';
import { type RunningInstance, residentRunRow } from '@/widgets/chat/rightpanel/runInstances';

/** Label key of a roster row's status readout. */
type MemberStateKey =
  | 'chat:panel.memberChatting'
  | 'chat:panel.memberBusy'
  | 'chat:delivery.failed'
  | 'chat:panel.finished'
  | 'chat:panel.memberIdle';

interface RosterRow {
  /** The run shown on this row: the live one, else the parked one. */
  run: RunningInstance | null;
  /** The settled run parked on this row, if any. */
  parked: RunningInstance | undefined;
  /** True when a live (polled) run occupies the row. */
  busy: boolean;
  /** True when the row's parked run failed. */
  failed: boolean;
  /** True when the row's run is the main conversational run. */
  isMain: boolean;
  /** Task runtime in seconds; null when the readout stays hidden. */
  elapsed: number | null;
  /** Label key for the row's status readout. */
  stateKey: MemberStateKey;
}

/** Resolve one roster row from the polled instances. A resident teammate's run
 *  is reflected in that teammate's own row; the main conversational run never
 *  parks as settled — when the turn ends Lucien simply returns to idle. */
function rosterRow(
  agentId: string,
  running: RunningInstance[],
  settled: RunningInstance[],
  now: number
): RosterRow {
  const live = running.find((r) => residentRunRow(r) === agentId);
  const parked = settled.find((r) => residentRunRow(r) === agentId && r.conversational !== true);
  const run = live ?? parked ?? null;
  const isMain = run?.conversational === true;
  const busy = live !== undefined;
  const failed = !busy && parked?.status === 'failed';
  // Elapsed is a task-runtime readout; the main conversational run spans the
  // whole session, so its age reads as a wrong "turn time" and stays hidden
  // behind the plain "chatting" state.
  const elapsed =
    live && !isMain && live.started_ts > 0
      ? Math.max(0, Math.round(now / 1000 - live.started_ts))
      : null;
  const stateKey: MemberStateKey = busy
    ? isMain
      ? 'chat:panel.memberChatting'
      : 'chat:panel.memberBusy'
    : failed
      ? 'chat:delivery.failed'
      : parked
        ? 'chat:panel.finished'
        : 'chat:panel.memberIdle';
  return { run, parked, busy, failed, isMain, elapsed, stateKey };
}

export function AgentRoster({
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
  return (
    <div className="chat-side__team">
      {AGENT_CATALOG.map((a) => {
        const row = rosterRow(a.id, running, settled, now);
        return (
          <button
            key={a.id}
            type="button"
            className={`chat-side__member${row.busy ? ' chat-side__member--busy' : ''}${!row.busy && row.parked ? ' chat-side__member--settled' : ''}${row.failed ? ' chat-side__member--failed' : ''}`}
            disabled={!row.run}
            title={(row.run?.goal ?? '') || undefined}
            onClick={() => {
              if (row.run && !row.isMain) onSelectRun(row.run);
            }}
          >
            <span className="chat-side__member-avatar" aria-hidden>
              <AgentCharacterHead agentId={a.id} look={{ x: 0, y: 0 }} isFocused={false} />
            </span>
            <span className="chat-side__membermain">
              <span className="chat-side__member-name">{personaDisplayName(a.id)}</span>
              {row.busy && row.run?.goal ? (
                <span className="chat-side__member-goal">{row.run.goal}</span>
              ) : null}
            </span>
            <span className="chat-side__member-state">
              {row.elapsed !== null ? (
                <span className="chat-side__member-elapsed">
                  {formatDurationSec(row.elapsed, t)}
                </span>
              ) : null}
              <span className="chat-side__member-dot" aria-hidden />
              <span className="chat-side__member-status">{t(row.stateKey)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
