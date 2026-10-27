/**
 * @file RawLogView
 * @description The chat page's log tab: every recorded LLM round of the
 * current session, each showing the raw request transcript (the exact
 * messages the model received) and the raw response, verbatim. Data comes
 * from GET /api/chat/rawllm (via bridge/chatSend) backed by the trajectory
 * store.
 *
 * Responsibilities:
 * - Show the load / empty / error state of the raw-round loader
 * - Hand the loaded rounds to the round list
 *
 * The round rendering lives in the rawlog/ submodules (loader hook, round
 * card, tab bar, round list) so this view stays a thin composition.
 */

import { useTranslation } from 'react-i18next';
import { useRawLlmRounds } from './rawlog/useRawLlmRounds';
import { RawLogRoundList } from './rawlog/RawLogRoundList';

export function RawLogView() {
  const { t } = useTranslation('chat');
  const { rounds, hidden, error, loading } = useRawLlmRounds();

  if (error) return <div className="chat-log chat-log--empty">⚠ {error}</div>;
  if (loading) return <div className="chat-log chat-log--empty">{t('chat:rawlog.loading')}</div>;
  if (rounds.length === 0) {
    return <div className="chat-log chat-log--empty">{t('chat:rawlog.empty')}</div>;
  }
  return <RawLogRoundList rounds={rounds} hidden={hidden} />;
}
