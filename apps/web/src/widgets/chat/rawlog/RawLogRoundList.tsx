/**
 * @file RawLogRoundList
 * @description The body of the chat page's raw log tab: the newest-first
 * window of recorded rounds, preceded by the note that says how many older
 * rounds stayed out of the window.
 *
 * Responsibilities:
 * - Render one card per round of the render window
 * - Report the rounds that were not rendered
 *
 * Constraints:
 * - The hidden-rounds note only appears when rounds were actually left out
 */

import { useTranslation } from 'react-i18next';
import type { RawLlmRound } from '@/bridge/chatSend';
import { RawLogRoundCard } from './RawLogRoundCard';

export function RawLogRoundList({ rounds, hidden }: { rounds: RawLlmRound[]; hidden: number }) {
  const { t } = useTranslation('chat');
  return (
    <div className="chat-log">
      {hidden > 0 ? (
        <div className="chat-log__hidden small muted" role="note">
          {t('chat:rawlog.hiddenRounds', { n: hidden, shown: rounds.length })}
        </div>
      ) : null}
      {rounds.map((r) => (
        <RawLogRoundCard key={`${r.run_id}-${r.round}-${r.ts}`} round={r} />
      ))}
    </div>
  );
}
