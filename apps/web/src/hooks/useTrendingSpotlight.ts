/**
 * @file useTrendingSpotlight
 * @description Spotlight state machine for hovering trending cards: streams an
 * agent intro for the hovered repo and schedules delayed hide on leave.
 *
 * Responsibilities:
 * - Run the hidden/visible/leaving phase machine with the 3s delayed hide
 *   and animation-length exit
 * - Stream the scout intro for the hovered repo, aborting stale
 *   generations and rendering stream errors as inline copy
 * - Track the hovered-card count so switching cards cancels the hide, and
 *   reset everything on period change or unmount
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamTrendingScoutIntro } from '@/api/overview';
import { i18n } from '@/i18n';
import type { LookTarget } from '@/components/agent/AgentAvatar';
import type { TrendingPeriod, TrendingRepo } from '@/api/types';
import { asSSETextDelta } from '@/utils/sseTextDelta';

/** Delay before the spotlight starts disappearing after all trending cards are left. */
export const TRENDING_SCOUT_LEAVE_DELAY_MS = 3000;
/** Must match the CSS transition duration. */
export const TRENDING_SCOUT_HIDE_ANIM_MS = 180;

export type TrendingSpotlightPhase = 'hidden' | 'visible' | 'leaving';

function repoKey(repo: TrendingRepo) {
  return `${repo.owner}/${repo.repo}`;
}

export function useTrendingSpotlight(period: TrendingPeriod) {
  const [phase, setPhase] = useState<TrendingSpotlightPhase>('hidden');
  const [repo, setRepo] = useState<TrendingRepo | null>(null);
  const [content, setContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [lookTarget, setLookTarget] = useState<LookTarget | null>(null);

  const leaveTimerRef = useRef<number | null>(null);
  const hideAnimTimerRef = useRef<number | null>(null);
  const streamGenRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const activeRepoKeyRef = useRef<string | null>(null);
  /** Number of trending cards currently hovered (briefly 0 while switching cards; enter cancels the hide). */
  const cardHoverCountRef = useRef(0);

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  const clearHideAnimTimer = useCallback(() => {
    if (hideAnimTimerRef.current !== null) {
      window.clearTimeout(hideAnimTimerRef.current);
      hideAnimTimerRef.current = null;
    }
  }, []);

  const abortStream = useCallback(() => {
    streamGenRef.current += 1;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsStreaming(false);
  }, []);

  const finishHide = useCallback(() => {
    abortStream();
    cardHoverCountRef.current = 0;
    setPhase('hidden');
    setRepo(null);
    setContent('');
    setLookTarget(null);
    activeRepoKeyRef.current = null;
  }, [abortStream]);

  const startHide = useCallback(() => {
    clearLeaveTimer();
    clearHideAnimTimer();
    setPhase('leaving');
    hideAnimTimerRef.current = window.setTimeout(() => {
      finishHide();
    }, TRENDING_SCOUT_HIDE_ANIM_MS);
  }, [clearHideAnimTimer, clearLeaveTimer, finishHide]);

  const scheduleHide = useCallback(() => {
    clearLeaveTimer();
    leaveTimerRef.current = window.setTimeout(() => {
      if (cardHoverCountRef.current > 0) return;
      startHide();
    }, TRENDING_SCOUT_LEAVE_DELAY_MS);
  }, [clearLeaveTimer, startHide]);

  const startStream = useCallback(
    async (target: TrendingRepo) => {
      const gen = ++streamGenRef.current;
      const key = repoKey(target);
      activeRepoKeyRef.current = key;
      setContent('');
      setIsStreaming(true);

      try {
        streamAbortRef.current?.abort();
        const stream = streamTrendingScoutIntro();

        for await (const event of stream) {
          if (streamGenRef.current !== gen || activeRepoKeyRef.current !== key) return;
          if (event.event === 'text_delta') {
            const delta = asSSETextDelta(event.data);
            setContent((prev) => prev + delta.content);
          } else if (event.event === 'error') {
            setContent(i18n.t('overview:trending.spotlightError'));
            break;
          }
        }
      } catch {
        if (streamGenRef.current === gen && activeRepoKeyRef.current === key) {
          setContent((prev) => prev || i18n.t('overview:trending.spotlightError'));
        }
      } finally {
        if (streamGenRef.current === gen && activeRepoKeyRef.current === key) {
          setIsStreaming(false);
        }
      }
    },
    // The stream API takes no arguments and does not depend on `period`;
    // a period change resets state via the useEffect above
    []
  );

  const onTrendingCardEnter = useCallback(
    (target: TrendingRepo, look: LookTarget) => {
      cardHoverCountRef.current += 1;
      clearLeaveTimer();
      clearHideAnimTimer();
      setLookTarget(look);

      const key = repoKey(target);
      const isNewRepo = activeRepoKeyRef.current !== key;

      setRepo(target);
      setPhase('visible');

      if (isNewRepo) {
        void startStream(target);
      }
    },
    [clearHideAnimTimer, clearLeaveTimer, startStream]
  );

  const onTrendingCardLeave = useCallback(() => {
    cardHoverCountRef.current = Math.max(0, cardHoverCountRef.current - 1);
    if (cardHoverCountRef.current === 0) {
      scheduleHide();
    }
  }, [scheduleHide]);

  const cancelHide = useCallback(() => {
    clearLeaveTimer();
    clearHideAnimTimer();
    setPhase((current) => (current === 'leaving' ? 'visible' : current));
  }, [clearHideAnimTimer, clearLeaveTimer]);

  const showForRepo = useCallback(
    (target: TrendingRepo, look: LookTarget) => {
      onTrendingCardEnter(target, look);
    },
    [onTrendingCardEnter]
  );

  const leaveTrendingCard = useCallback(() => {
    onTrendingCardLeave();
  }, [onTrendingCardLeave]);

  const updateLook = useCallback((look: LookTarget) => {
    setLookTarget(look);
  }, []);

  useEffect(() => {
    cardHoverCountRef.current = 0;
    clearLeaveTimer();
    clearHideAnimTimer();
    finishHide();
  }, [period, clearHideAnimTimer, clearLeaveTimer, finishHide]);

  useEffect(
    () => () => {
      clearLeaveTimer();
      clearHideAnimTimer();
      abortStream();
    },
    [abortStream, clearHideAnimTimer, clearLeaveTimer]
  );

  return {
    phase,
    repo,
    content,
    isStreaming,
    lookTarget,
    showForRepo,
    leaveTrendingCard,
    updateLook,
    scheduleHide,
    cancelHide,
  };
}
