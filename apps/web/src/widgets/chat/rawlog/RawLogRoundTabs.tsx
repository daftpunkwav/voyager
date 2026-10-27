/**
 * @file RawLogRoundTabs
 * @description The tab bar of one recorded raw LLM round: switches between
 * the provider's wire request body, the request the model received, and the
 * raw response. The wire tab only exists for rounds recorded with it.
 *
 * Responsibilities:
 * - Render the recorded bodies of a round as a tablist
 * - Mark the active tab and report the picked tab to the owning card
 *
 * Constraints:
 * - The wire tab stays hidden for rounds recorded without a wire body
 * - Tab order (wire, request, response) is part of the rendered output
 */

import { useTranslation } from 'react-i18next';

/** The recorded bodies a round can show. */
export type RawLogRoundTab = 'request' | 'response' | 'wire';

export function RawLogRoundTabs({
  active,
  hasWire,
  onPick,
}: {
  active: RawLogRoundTab;
  hasWire: boolean;
  onPick: (tab: RawLogRoundTab) => void;
}) {
  const { t } = useTranslation('chat');
  return (
    <div className="chat-log__tabs" role="tablist">
      {hasWire ? (
        <button
          type="button"
          role="tab"
          aria-selected={active === 'wire'}
          className={`chat-log__tab${active === 'wire' ? ' is-active' : ''}`}
          onClick={() => onPick('wire')}
        >
          {t('chat:rawlog.wire')}
        </button>
      ) : null}
      <button
        type="button"
        role="tab"
        aria-selected={active === 'request'}
        className={`chat-log__tab${active === 'request' ? ' is-active' : ''}`}
        onClick={() => onPick('request')}
      >
        {t('chat:rawlog.request')}
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={active === 'response'}
        className={`chat-log__tab${active === 'response' ? ' is-active' : ''}`}
        onClick={() => onPick('response')}
      >
        {t('chat:rawlog.response')}
      </button>
    </div>
  );
}
