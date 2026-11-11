/**
 * @file GenericRunList
 * @description The panel's generic run list: the runs no resident teammate
 * owns (unnamed or custom-persona runs), listed below the roster divider
 * next to the runs that just settled.
 *
 * Responsibilities:
 * - Render one row per generic run with its avatar, goal and elapsed time
 * - Mark settled and failed runs through the row's modifier class
 * - Open the run's execution view when a row is clicked
 *
 * Constraints:
 * - Presentation only: the polled instances arrive through props, this
 *   component never polls or reads the store itself.
 */

import { useTranslation } from 'react-i18next';
import { personaDisplayName } from '@/constants/personas';
import { AgentCharacterHead } from '@/components/agent/avatars/AgentCharacterHead';
import { formatDurationSec } from '@/utils/trajectory';
import type { RunningInstance } from '@/widgets/chat/rightpanel/runInstances';

export function GenericRunList({
  runs,
  now,
  onSelectRun,
}: {
  runs: RunningInstance[];
  now: number;
  onSelectRun: (run: RunningInstance | null) => void;
}) {
  const { t } = useTranslation('chat');
  return (
    <ul className="chat-side__agents">
      {runs.map((r) => {
        const settledRow = r.status !== 'running';
        const elapsed =
          r.started_ts > 0 ? Math.max(0, Math.round(now / 1000 - r.started_ts)) : null;
        const isMain = r.conversational === true;
        const persona = r.persona ?? '';
        return (
          <li key={`${r.id}-${r.status}`}>
            <button
              type="button"
              className={`chat-side__agent${settledRow ? ' chat-side__agent--settled' : ''}${r.status === 'failed' ? ' chat-side__agent--failed' : ''}`}
              title={t('chat:panel.badgeTitle', { goal: r.goal, status: r.status })}
              onClick={() => onSelectRun(isMain ? null : r)}
            >
              {isMain ? (
                <span className="chat-side__pulse" aria-hidden />
              ) : (
                <span className="chat-side__agent-avatar" aria-hidden>
                  <AgentCharacterHead
                    agentId={persona || 'orchestrator'}
                    look={{ x: 0, y: 0 }}
                    isFocused={false}
                  />
                </span>
              )}
              <span className="chat-side__agentmain">
                <span className="chat-side__agent-name">
                  {isMain
                    ? t('chat:panel.mainAgent')
                    : settledRow
                      ? `${persona || r.name} · ${r.status === 'failed' ? t('chat:delivery.failed') : t('chat:panel.finished')}`
                      : persona
                        ? personaDisplayName(persona)
                        : r.name}
                </span>
                {r.goal ? <span className="chat-side__agent-goal">{r.goal}</span> : null}
              </span>
              {elapsed !== null && !settledRow ? (
                <span className="chat-side__agent-elapsed">{formatDurationSec(elapsed, t)}</span>
              ) : null}
              <span className="chat-side__agent-stop">{t('chat:panel.viewRun')}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
