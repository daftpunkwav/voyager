/**
 * @file chatStore.ts
 * @description Conversation state: message stream (user/agent/system), task progress
 * cards, pending questions, connection and thinking indicators, plus the
 * execution-trajectory trails (closed per-turn step groups rebuilt from
 * persisted rows via applyTrajectory, live turns via steps/lastSteps).
 *
 * The chat page and the persistent floating window are two views of the same
 * conversation, so this store is shared by both —
 * widgets never depend on page-private implementations.
 *
 * Multi-session model: the top-level timeline fields (messages/trails/steps/
 * streaming/thinking…) ARE the active session's view, so existing consumers
 * stay unchanged; when the user switches sessions the active view is archived
 * into `lanes` and the target lane is hydrated back. SSE events carry a
 * `session` field: events for the active session flow through the top-level
 * path, events for inactive lanes append into their archived snapshot (final
 * messages are never lost; live progress for background lanes is reduced to
 * the message that lands). Session-less events (task results, policy notices)
 * stay global and surface in the active view.
 *
 * Responsibilities:
 * - Hold the active session's conversation timeline shared by the chat
 *   page and the persistent floating window
 * - Dispatch SSE events into state: agent messages/asks/steps, streaming
 *   deltas, task progress cards, and note artifacts — routed per session
 * - Rebuild history with a seq-window replacement so live messages and
 *   locally synthesized bubbles are never wiped; backward pages prepend
 *   older history (dedup by seq) with has_more tracking
 * - Track connection, thinking, current-step, and pending-question state
 * - Track the session list and the active/archive lane switching
 *
 * This module must not depend on UI-layer components.
 */

import { create } from 'zustand';
import { i18n } from '@/i18n';
import { routes } from '@/utils/routes';
import { groupTrails } from '@/utils/trajectory';

export interface ChatMessage {
  seq: number;
  role: 'user' | 'agent' | 'system';
  content: string;
  ts?: number;
}

export interface ProgressCard {
  key: string; // source_id / job_id
  label: string;
  progress: number;
  stage: string;
  status: 'running' | 'completed' | 'failed';
  error?: string;
  /** payload-provided resource type (doc/repo/web…) deciding whether the resource detail page is reachable */
  kind?: string;
  /** Precomputed resource-detail route; omitted when there is no detail page (e.g. a graph job_id) — no fake buttons */
  link?: string;
}

/** Note artifact card (note.created): clicking navigates to /notes?note=<id>. */
export interface NoteArtifact {
  seq: number;
  noteId: string;
  title: string;
}

export interface PendingQuestion {
  questionId: string;
  prompt: string;
  /** The model picks the answer form; unknown kinds degrade to free text. */
  kind: 'text' | 'choice' | 'multi_choice' | 'slider' | 'rating' | 'confirm';
  options: string[];
  min: number | null;
  max: number | null;
}

/** Live step for agent.step: only the current step is shown; a new step overwrites the old. */
export interface CurrentStep {
  /** Tool name or round-N */
  name: string;
  /** Name of the subagent doing the work (chat / dispatch name) */
  subagent: string;
}

/** One execution-trajectory entry (agent.step): kind llm = a ReAct round,
 *  kind tool = a finished tool call. Live-only data — rebuilt turns after
 *  refresh do not replay steps. */
export interface TurnStep {
  seq: number;
  kind: string;
  name: string;
  summary: string;
  subagent: string;
  ts?: number;
  /** Structured facts (M3+ backends; absent on older rows): */
  runId?: string;
  /** Tool steps: provider call id, capped args JSON, outcome, latency. */
  toolCallId?: string;
  args?: string;
  ok?: boolean;
  ms?: number;
  title?: string;
  truncated?: boolean;
  /** LLM round steps: round number, requested tools, usage, latency. */
  round?: number;
  toolCalls?: string[];
  inputTokens?: number;
  outputTokens?: number;
  ttftMs?: number;
  /** LLM round steps: full round output (backend-capped) for the thinking block. */
  text?: string;
  textTruncated?: boolean;
}

/** Streaming typing for agent.delta: holds only the current delta of the main
 *  conversation; when agent.message arrives the text settles into a real message
 *  and this slot clears. A round change restarts it. */
export interface StreamingText {
  text: string;
  round: number;
  subagent: string;
}

/** Lead-in text of an already-finished round (agent.delta, frozen when the
 *  next round starts). Kept for the live turn only so the inline trace can
 *  interleave paragraphs and tool groups like a mainstream agent UI. */
export interface RoundText {
  round: number;
  text: string;
}

/** Common shape of SSE frames / history rows (Event.to_dict + seq). */
export interface ChatEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  ts?: number;
  trace_id?: string;
}

/** One closed turn rebuilt from persisted rows (see utils/trajectory). */
export interface TurnTrail {
  msgSeq: number;
  userText: string;
  steps: TurnStep[];
}

/** One row of the session list (agent.list_sessions payload). */
export interface SessionRow {
  session_id: string;
  title: string;
  persona?: string;
  status: string;
  active?: boolean;
  turns?: number | null;
  updated_at?: number | null;
}

/** Archived state of an inactive session (the active session lives in the
 *  top-level fields; switching swaps them). */
interface LaneSnapshot {
  messages: ChatMessage[];
  hasMoreHistory: boolean;
  trails: TurnTrail[];
  steps: TurnStep[];
  lastSteps: TurnStep[];
  streaming: StreamingText | null;
  thinking: boolean;
  /** History/trajectory backfill already ran for this lane. */
  loaded: boolean;
}

function emptyLane(): LaneSnapshot {
  return {
    messages: [],
    hasMoreHistory: false,
    trails: [],
    steps: [],
    lastSteps: [],
    streaming: null,
    thinking: false,
    loaded: false,
  };
}

/** agent.step payload -> TurnStep (live SSE and trajectory backfill share it). */
export function toTurnStep(ev: ChatEvent): TurnStep {
  const p = ev.payload ?? {};
  const detail =
    p.detail && typeof p.detail === 'object' ? (p.detail as Record<string, unknown>) : {};
  const num = (v: unknown): number | undefined =>
    typeof v === 'number' && Number.isFinite(v) ? v : undefined;
  const str = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined);
  const strList = (v: unknown): string[] | undefined =>
    Array.isArray(v) && v.every((x) => typeof x === 'string') ? (v as string[]) : undefined;
  return {
    seq: ev.seq,
    kind: String(p.kind ?? ''),
    name: String(p.name ?? ''),
    summary: String(p.summary ?? ''),
    subagent: String(p.subagent ?? ''),
    ts: ev.ts,
    runId: str(p.run_id),
    toolCallId: str(detail.tool_call_id),
    args: str(detail.args),
    ok: typeof detail.ok === 'boolean' ? detail.ok : undefined,
    ms: num(detail.ms),
    title: str(detail.title),
    truncated: detail.truncated === true ? true : undefined,
    round: num(detail.round),
    toolCalls: strList(detail.tool_calls),
    inputTokens: num(detail.input_tokens),
    outputTokens: num(detail.output_tokens),
    ttftMs: num(detail.ttft_ms),
    text: str(detail.text),
    textTruncated: detail.text_truncated === true ? true : undefined,
  };
}

interface ChatState {
  /** Session list (agent.list_sessions) and the id of the open lane; '' means
   *  the sessions capability has not answered yet (legacy global view). */
  sessions: SessionRow[];
  activeSessionId: string;
  /** Whether the active lane's history/trajectory backfill already ran. */
  activeLoaded: boolean;
  /** Archived views of inactive sessions. */
  lanes: Record<string, LaneSnapshot>;
  messages: ChatMessage[];
  /** Older history pages exist (set by the latest history/prepend response). */
  hasMoreHistory: boolean;
  /** An older-page fetch is in flight. */
  historyLoading: boolean;
  cards: Record<string, ProgressCard>;
  cardOrder: string[];
  artifacts: NoteArtifact[];
  question: PendingQuestion | null;
  connected: boolean;
  thinking: boolean;
  /** Current tool step (agent.step); cleared on agent.message / round end */
  currentStep: CurrentStep | null;
  /** Execution trajectory of the current turn (agent.step appends; live-only). */
  steps: TurnStep[];
  /** Closed per-turn trails rebuilt from persisted rows (refresh-safe);
   *  the latest closed turn duplicates lastSteps by reference. */
  trails: TurnTrail[];
  /** Trajectory of the previous finished turn, shown collapsed by the timeline. */
  lastSteps: TurnStep[];
  /** Frozen lead-in texts of finished rounds of the live turn (round -> text). */
  roundTexts: RoundText[];
  /** Current streaming typing (agent.delta); cleared by agent.message, restarted on round change */
  streaming: StreamingText | null;
  /** History API messages (user.message/agent.message) -> message stream; does not trigger the thinking indicator.
   *  hasMore records whether older pages exist for backward paging. */
  applyHistory: (events: ChatEvent[], hasMore?: boolean) => void;
  /** Prepend one older history page (backward paging); duplicates are dropped,
   *  live messages and locally synthesized bubbles stay untouched. */
  prependHistory: (events: ChatEvent[], hasMore: boolean) => void;
  /** Backfill persisted steps (/api/chat/trajectory) and regroup closed
   *  turns; the still-open turn merges into the live slot. */
  applyTrajectory: (events: ChatEvent[]) => void;
  /** Backward-page fetch in flight (top loader indicator + trigger re-entry guard). */
  setHistoryLoading: (v: boolean) => void;
  /** SSE event dispatch (agent.ask, task.*, agent.message, note.created, etc.); pure state transitions, unit-testable. */
  dispatch: (ev: ChatEvent) => void;
  appendLocal: (msg: ChatMessage) => void;
  /** System notice (control-plane events like hard-stop/timeout, local seq); does not touch
   *  thinking — the caller decides the thinking state. */
  addSystem: (content: string) => void;
  setConnected: (v: boolean) => void;
  clearQuestion: () => void;
  /** Round end (hard-stop / send failure / subtask wrap-up) clears the thinking and typing
   *  slots; besides appendLocal/dispatch this is the only other write path to thinking. */
  clearThinking: () => void;
  /** Session list from the capability; switches the active lane when the
   *  backend's active session differs from the currently open one. */
  setSessions: (rows: SessionRow[], activeId: string) => void;
  /** Archive the open view and hydrate the target lane; returns whether the
   *  target lane already had its history backfill (caller fetches when not). */
  switchSession: (sessionId: string) => boolean;
  /** Route one session-scoped SSE event into its lane (active: top-level
   *  path; inactive: archived snapshot update, never dropped). */
  dispatchToLane: (sessionId: string, ev: ChatEvent) => void;
}

function taskKey(payload: Record<string, unknown>): string {
  return String(payload.source_id ?? payload.job_id ?? '');
}

/** Insert or replace a closed-turn trail by closing message seq (cap 100). */
function upsertTrail(trails: TurnTrail[], trail: TurnTrail): TurnTrail[] {
  const next = trails.filter((t) => t.msgSeq !== trail.msgSeq);
  next.push(trail);
  next.sort((a, b) => a.msgSeq - b.msgSeq);
  return next.slice(-100);
}

/** History rows (user.message/agent.message events) -> message stream items. */
function historyToMessages(events: ChatEvent[]): ChatMessage[] {
  return events
    .filter((e) => e.type === 'user.message' || e.type === 'agent.message')
    .map((e) => ({
      seq: e.seq,
      role: (e.type === 'user.message' ? 'user' : 'agent') as ChatMessage['role'],
      content: String(e.payload?.content ?? ''),
      ts: e.ts,
    }));
}

/** Latest user text above the timeline tail (trail attribution helper). */
function lastUserText(messages: ChatMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user' && messages[i].seq > 0 && messages[i].content) {
      return messages[i].content;
    }
  }
  return '';
}

/** Card label priority: project → title → kind → key.
 *  sources progress events often lack project, and using the key directly would show a
 *  uuid; readable fields like kind act as the fallback. */
function taskLabel(payload: Record<string, unknown>, fallback: string): string {
  for (const field of ['project', 'title', 'kind'] as const) {
    const v = payload[field];
    if (v !== undefined && v !== null && String(v) !== '') return String(v);
  }
  return fallback;
}

/** source_id -> resource detail route; tasks with only a job_id (e.g. graph) have no detail page, so no link is fabricated.
 *  When kind is missing, routes.sourceOf falls to the repo page: currently only repo worker task events omit kind, which happens to be correct. */
function taskLink(payload: Record<string, unknown>): string | undefined {
  const sid = payload.source_id;
  if (sid === undefined || sid === null || String(sid) === '') return undefined;
  const kind = payload.kind === undefined ? undefined : String(payload.kind);
  return routes.sourceOf(kind, String(sid));
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: '',
  activeLoaded: false,
  lanes: {},
  messages: [],
  hasMoreHistory: false,
  historyLoading: false,
  cards: {},
  cardOrder: [],
  artifacts: [],
  question: null,
  connected: false,
  thinking: false,
  currentStep: null,
  steps: [],
  trails: [],
  lastSteps: [],
  roundTexts: [],
  streaming: null,

  setSessions: (rows, activeId) => {
    set({ sessions: rows, activeSessionId: activeId });
  },

  switchSession: (sessionId) => {
    const s = get();
    if (sessionId === s.activeSessionId) return s.activeLoaded;
    const archived: LaneSnapshot = {
      messages: s.messages,
      hasMoreHistory: s.hasMoreHistory,
      trails: s.trails,
      steps: s.steps,
      lastSteps: s.lastSteps,
      streaming: s.streaming,
      thinking: s.thinking,
      loaded: s.activeLoaded,
    };
    const lane = s.lanes[sessionId] ?? emptyLane();
    set({
      activeSessionId: sessionId,
      lanes: { ...s.lanes, [s.activeSessionId]: archived },
      messages: lane.messages,
      hasMoreHistory: lane.hasMoreHistory,
      trails: lane.trails,
      steps: lane.steps,
      lastSteps: lane.lastSteps,
      roundTexts: [],
      streaming: lane.streaming,
      thinking: lane.thinking,
      activeLoaded: lane.loaded,
      // Per-turn visual slots reset on a switch; per-session state stays
      currentStep: null,
    });
    return lane.loaded;
  },

  dispatchToLane: (sessionId, ev) => {
    const lane = get().lanes[sessionId];
    if (!lane) return; // no archived view yet: the backfill will pick the rows up
    const p = ev.payload ?? {};
    if (ev.type === 'agent.message') {
      const next: LaneSnapshot = {
        ...lane,
        thinking: false,
        streaming: null,
        lastSteps: lane.steps,
        steps: [],
        messages: [
          ...lane.messages,
          { seq: ev.seq, role: 'agent', content: String(p.content ?? ''), ts: ev.ts },
        ],
      };
      set({ lanes: { ...get().lanes, [sessionId]: next } });
    } else if (ev.type === 'agent.delta') {
      const round = Number(p.round ?? 1);
      const prev = lane.streaming;
      const same = prev !== null && prev.round === round;
      set({
        lanes: {
          ...get().lanes,
          [sessionId]: {
            ...lane,
            thinking: true,
            streaming: {
              text: (same ? prev.text : '') + String(p.text ?? ''),
              round,
              subagent: String(p.subagent ?? ''),
            },
          },
        },
      });
    }
    // agent.step for background lanes is dropped: progress visuals matter
    // only for the open lane, and the final message still lands above.
  },

  applyHistory: (events, hasMore = false) => {
    const msgs = historyToMessages(events);
    // While a history request is in flight, live SSE messages may already sit in the
    // timeline: the replacement only covers the history range (seq <= last history
    // seq); newer live messages and locally synthesized bubbles (seq < 0) are kept,
    // otherwise the backfill would wipe just-arrived messages
    const maxSeq = msgs.length ? msgs[msgs.length - 1].seq : 0;
    const live = get().messages.filter((m) => m.seq < 0 || m.seq > maxSeq);
    set({ messages: [...msgs, ...live], hasMoreHistory: hasMore, activeLoaded: true });
  },

  prependHistory: (events, hasMore) => {
    const older = historyToMessages(events);
    const existing = get().messages;
    // Dedup by seq: the window may overlap the current history if events
    // landed between two page fetches
    const seen = new Set(existing.map((m) => m.seq));
    const fresh = older.filter((m) => !seen.has(m.seq));
    set({
      messages: [...fresh, ...existing],
      hasMoreHistory: hasMore,
      historyLoading: false,
    });
  },

  setHistoryLoading: (v) => set({ historyLoading: v }),

  applyTrajectory: (events) => {
    const incoming = events.filter((e) => e.type === 'agent.step').map(toTurnStep);
    const seen = new Set(get().steps.map((s) => s.seq));
    const merged = [...get().steps, ...incoming.filter((s) => !seen.has(s.seq))]
      .sort((a, b) => a.seq - b.seq)
      .slice(-500);
    const { trails, openSteps } = groupTrails(get().messages, merged);
    let next = get().trails;
    for (const t of trails) next = upsertTrail(next, t);
    set({ trails: next, steps: openSteps.slice(-200) });
  },

  dispatch: (ev) => {
    const p = ev.payload;
    // Session routing: an event stamped with another session's id goes to
    // that lane's archived snapshot (final messages must never be lost);
    // session-less events (task results, policy notices) stay global.
    const evSession = String(p?.session ?? '');
    if (evSession && evSession !== get().activeSessionId) {
      get().dispatchToLane(evSession, ev);
      return;
    }
    switch (ev.type) {
      case 'agent.message': {
        // Clear question too: the agent speaking again means it is no longer waiting
        // for an answer (e.g. continuing with defaults after an answer timeout), so
        // the dialog must not stay stuck on a question the backend dropped;
        // currentStep clears as well: any round output means "no tool running";
        // streaming settles and clears: the real message has arrived, the typing slot is done.
        // The turn's step trajectory folds into lastSteps and the timeline collapses.
        // The closed turn also lands in trails (msgSeq-upsert, so refresh
        // rebuilds and live appends compose without duplicates).
        const prevSteps = get().steps;
        const prevMessages = get().messages;
        const userText = lastUserText(prevMessages);
        const trails =
          prevSteps.length > 0
            ? upsertTrail(get().trails, { msgSeq: ev.seq, userText, steps: prevSteps })
            : get().trails;
        set({
          thinking: false,
          question: null,
          currentStep: null,
          streaming: null,
          lastSteps: prevSteps,
          roundTexts: [],
          steps: [],
          trails,
          messages: [
            ...get().messages,
            {
              seq: ev.seq,
              role: 'agent',
              content: String(p.content ?? ''),
              ts: ev.ts,
            },
          ],
        });
        break;
      }
      case 'agent.ask': {
        // Options are rendered as button children: normalize defensively — the
        // backend used to pass the LLM's {"content": ...} objects through, and a
        // non-string option crashes the whole route
        const rawOptions = Array.isArray(p.options) ? p.options : [];
        const options = rawOptions.map((o) =>
          typeof o === 'string'
            ? o
            : o && typeof o === 'object'
              ? ((['content', 'label', 'value', 'text']
                  .map((k) => (o as Record<string, unknown>)[k])
                  .find((v) => typeof v === 'string' && v.trim()) as string | undefined) ??
                JSON.stringify(o))
              : String(o ?? '')
        );
        set({
          question: {
            questionId: String(p.question_id),
            prompt: String(p.prompt ?? ''),
            kind: (p.kind as PendingQuestion['kind']) ?? 'confirm',
            options,
            min: (p.min as number | null) ?? null,
            max: (p.max as number | null) ?? null,
          },
        });
        break;
      }
      case 'agent.navigate': {
        set({
          messages: [
            ...get().messages,
            {
              seq: ev.seq,
              role: 'system',
              content: i18n.t('chat:store.navigated', { path: String(p.path ?? '') }),
              ts: ev.ts,
            },
          ],
        });
        break;
      }
      case 'note.created': {
        // Note artifact card (appears whether the user or the agent saved it; click navigates to the notes page)
        set({
          artifacts: [
            ...get().artifacts,
            {
              seq: ev.seq,
              noteId: String(p.note_id ?? ''),
              title: String(p.title ?? i18n.t('chat:store.untitledNote')),
            },
          ].filter((a) => a.noteId),
        });
        break;
      }
      case 'agent.step': {
        // Live tool/round step: a new step overwrites the old one for the
        // StepLine-style slot, and the full trajectory grows for the timeline.
        const prev = get().steps;
        const step = toTurnStep(ev);
        // SSE replays (lagged catch-up, reconnect) may re-deliver a step: the
        // append must stay idempotent by seq, unlike the overwrite-only slot
        const steps = prev.some((s) => s.seq === step.seq) ? prev : [...prev, step].slice(-200);
        set({
          currentStep: { name: step.name, subagent: step.subagent },
          steps,
        });
        break;
      }
      case 'agent.delta': {
        // Streaming typing: accumulate within the same round; a round change (a new
        // round after tool rounds) freezes the finished round's lead-in text for the
        // inline trace and restarts the slot — lead-in text of intermediate rounds
        // never carries into the final round, agent.message is the authoritative message
        const round = Number(p.round ?? 1);
        const prev = get().streaming;
        const same = prev !== null && prev.round === round;
        const roundTexts =
          !same && prev && prev.text
            ? [...get().roundTexts, { round: prev.round, text: prev.text }].slice(-20)
            : get().roundTexts;
        set({
          roundTexts,
          streaming: {
            text: (same ? prev.text : '') + String(p.text ?? ''),
            round,
            subagent: String(p.subagent ?? ''),
          },
        });
        break;
      }
      case 'task.progress':
      case 'task.enqueued': {
        const key = taskKey(p);
        if (!key) break;
        const cards = { ...get().cards };
        if (!cards[key]) get().cardOrder.push(key);
        const prev = cards[key];
        cards[key] = {
          key,
          label: taskLabel(p, prev?.label ?? key),
          progress: Number(p.progress ?? prev?.progress ?? 0),
          stage: String(p.stage ?? prev?.stage ?? i18n.t('chat:store.stageRunning')),
          status: 'running',
          kind: p.kind === undefined ? prev?.kind : String(p.kind),
          link: taskLink(p) ?? prev?.link,
        };
        set({ cards, cardOrder: [...get().cardOrder] });
        break;
      }
      case 'task.completed':
      case 'task.failed': {
        const key = taskKey(p);
        if (!key) break;
        const failed = ev.type === 'task.failed';
        const cards = { ...get().cards };
        const prev = cards[key];
        // Create a card even without an earlier progress card: completion/failure are
        // terminal facts and must not be swallowed for lack of a predecessor
        if (!prev) get().cardOrder.push(key);
        cards[key] = {
          key,
          label: taskLabel(p, prev?.label ?? key),
          progress: failed ? (prev?.progress ?? 0) : 1,
          stage: String(
            p.stage ?? (failed ? (prev?.stage ?? '') : i18n.t('chat:store.stageCompleted'))
          ),
          status: failed ? 'failed' : 'completed',
          error: p.error ? String(p.error) : undefined,
          kind: p.kind === undefined ? prev?.kind : String(p.kind),
          link: taskLink(p) ?? prev?.link,
        };
        set({ cards, cardOrder: [...get().cardOrder] });
        break;
      }
      default:
        break;
    }
  },

  appendLocal: (msg) => {
    set({ thinking: true, messages: [...get().messages, msg] });
  },

  addSystem: (content) => {
    set({
      messages: [...get().messages, { seq: -Date.now(), role: 'system', content }],
    });
  },

  setConnected: (v) => set({ connected: v }),
  clearQuestion: () => set({ question: null }),
  // Turn over (hard-stop / send failure): fold the live trajectory like a normal
  // turn end so the timeline never stays in "running" shape. The interrupted
  // turn also lands in trails under a synthetic negative key (it has no
  // closing message), so the trajectory view keeps it after later turns.
  clearThinking: () =>
    set((s) => ({
      thinking: false,
      streaming: null,
      roundTexts: [],
      lastSteps: s.steps.length ? s.steps : s.lastSteps,
      steps: [],
      trails:
        s.steps.length > 0
          ? upsertTrail(s.trails, {
              msgSeq: -Date.now(),
              userText: lastUserText(s.messages),
              steps: s.steps,
            })
          : s.trails,
    })),
}));
