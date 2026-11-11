/**
 * @file useRawLlmRounds
 * @description Data wiring of the chat page's raw log tab: loads the active
 * session's recorded raw LLM rounds (GET /api/chat/rawllm, via
 * bridge/chatSend) and narrows them to the window the tab renders.
 *
 * Responsibilities:
 * - Load the active session's rounds and surface the load error
 * - Keep the render window bounded (the newest rounds only)
 * - Report how many rounds stayed out of the rendered window
 *
 * Constraints:
 * - Round bodies are verbatim transcripts (tens of KB each); only the
 *   rendered window is fetched, older rounds stay recorded server-side
 * - A session-less session (sessions capability unavailable) resolves to an
 *   empty page instead of surfacing the backend error text
 */

import { useEffect, useMemo, useState } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { fetchRawLlmRounds, type RawLlmRound } from '@/bridge/chatSend';

/** Newest rounds rendered. The endpoint returns every recorded round of the
 *  session with full verbatim bodies; a long session can total tens of MB and
 *  rendering it all as <pre> DOM freezes the tab. Older rounds stay recorded
 *  server-side — only the rendered window is capped. */
const RENDER_LIMIT = 50;

/** One fetched page of rounds plus the session's total round count. */
interface RawLlmRoundsPage {
  rounds: RawLlmRound[];
  total: number;
}

/** What the raw log tab needs to render. */
export interface RawLlmRoundsState {
  /** The newest-first window of rounds to render (empty until loaded). */
  rounds: RawLlmRound[];
  /** Rounds left out: older than the fetched page and older than the window. */
  hidden: number;
  /** The load failure message, if the last load failed. */
  error: string | null;
  /** True while the active session's first page is still loading. */
  loading: boolean;
}

/** The newest-first render window of a fetched page, plus the number of
 *  rounds that stayed out of it. */
function selectRenderWindow(
  rounds: RawLlmRound[] | null,
  total: number
): { visible: RawLlmRound[]; hidden: number } {
  if (!rounds) return { visible: [], hidden: 0 };
  const visible = [...rounds].reverse().slice(0, RENDER_LIMIT);
  // `beyond` counts what is not shown at all: older than the backend page AND
  // older than the render window.
  const beyond = Math.max(0, total - rounds.length);
  return { visible, hidden: rounds.length - visible.length + beyond };
}

/** Load the active session's raw LLM rounds for the raw log tab. */
export function useRawLlmRounds(): RawLlmRoundsState {
  const activeId = useChatStore((s) => s.activeSessionId);
  const [page, setPage] = useState<RawLlmRoundsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setError(null);
    if (!activeId) {
      // Legacy session-less view (sessions capability unavailable): the rawllm
      // API requires a session or run id, so fetching would 400 — show the
      // empty state instead of surfacing the backend error text.
      setPage({ rounds: [], total: 0 });
      return () => {
        cancelled = true;
      };
    }
    // Fetch exactly the rendered window: round bodies are verbatim transcripts
    // (tens of KB each), so pulling the backend's default 200-round page for a
    // 50-round render would transfer and JSON-parse 4x more than is shown.
    // `total` still reports the session's full count, so the hidden-rounds
    // note stays correct.
    fetchRawLlmRounds(activeId, RENDER_LIMIT)
      .then((data) => {
        if (!cancelled) setPage(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const selection = useMemo(
    () => selectRenderWindow(page?.rounds ?? null, page?.total ?? 0),
    [page]
  );

  return {
    rounds: selection.visible,
    hidden: selection.hidden,
    error,
    loading: page === null && error === null,
  };
}
