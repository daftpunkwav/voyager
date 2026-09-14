/**
 * @file TurnTrace
 * @description Inline execution trace for the chat stream, styled after
 * mainstream agent UIs: each ReAct round renders its lead-in paragraph above
 * a collapsible group ("思考 1 次 · 工具 2 次") holding that round's think
 * marker and tool rows. The live turn's tail group stays expanded while tool
 * work is happening and auto-collapses the moment output text starts
 * streaming; a user click overrides until the turn ends. Closed turns render
 * as one collapsed group keyed off the persisted trail, expandable in place.
 *
 * Data: live steps + frozen round texts from chatStore (live-only, a refresh
 * rebuilds closed turns from trails instead); closed turns pass steps in.
 */

import { Fragment, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type RoundText, type TurnStep, useChatStore } from '@/stores/chatStore';
import { formatDurationSec } from '@/utils/trajectory';
import { StepDetail } from '@/widgets/chat/StepDetail';
import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';

/** Humanize a tool identifier for display: `notes__create_note` maps to the
 *  localized action label (chat:tool.create_note, e.g. "创建笔记"/"Create note");
 *  unknown capabilities fall back to the bare capability name with underscores
 *  spaced out. The raw domain__capability name stays internal on purpose: it is
 *  the namespace separator the activation/allow-list mechanics parse. */
export function toolLabel(
  name: string,
  t: (key: string, opts?: Record<string, unknown>) => string
): string {
  const idx = name.indexOf('__');
  const cap = idx >= 0 ? name.slice(idx + 2) : name;
  return t(`chat:tool.${cap}`, { defaultValue: cap.replace(/_/g, ' ') });
}

type IconName =
  | 'terminal'
  | 'globe'
  | 'graph'
  | 'search'
  | 'list'
  | 'chat'
  | 'agent'
  | 'sparkle'
  | 'pencil'
  | 'file'
  | 'box';

/** Keyword -> icon mapping for tool rows; first match wins, so broad write
 *  verbs come late and specific surfaces (web/graph/shell) come first. */
const TOOL_ICON_RULES: Array<[RegExp, IconName]> = [
  [/shell|exec/i, 'terminal'],
  [/page|url|web|clip/i, 'globe'],
  [/graph|node|subgraph|merge|relationship|link|tag|neighbor|backlink/i, 'graph'],
  [/search|grep|find|query|glob|expand|resolve|recall|memory|context/i, 'search'],
  [/todo/i, 'list'],
  [/ask|reach/i, 'chat'],
  [/spawn|wait_|subagent/i, 'agent'],
  [/skill/i, 'sparkle'],
  [/write|edit|create|save|set|import|rename|reorder|mark|restore|purge|delete|drop|empty|batch|activate|sort/i, 'pencil'],
  [/read|get|list|show|view|export|toc|stats|info|defaults|test|usage|version/i, 'file'],
];

function iconForStep(step: TurnStep): IconName {
  if (step.kind !== 'tool') return 'sparkle';
  const idx = step.name.indexOf('__');
  const cap = idx >= 0 ? step.name.slice(idx + 2) : step.name;
  for (const [re, icon] of TOOL_ICON_RULES) {
    if (re.test(cap)) return icon;
  }
  return 'box';
}

/** 14px stroke icons (currentColor); tiny enough to sit inline in trace rows. */
function TraceIcon({ name }: { name: IconName }) {  const common = {
    width: 14,
    height: 14,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
  switch (name) {
    case 'terminal':
      return (
        <svg {...common}>
          <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
          <path d="M7.5 9.5l3 2.5-3 2.5M12.5 15H16" />
        </svg>
      );
    case 'globe':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M3.5 12h17M12 3.5c2.6 2.3 3.9 5.2 3.9 8.5s-1.3 6.2-3.9 8.5c-2.6-2.3-3.9-5.2-3.9-8.5s1.3-6.2 3.9-8.5z" />
        </svg>
      );
    case 'graph':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="2.6" />
          <circle cx="18" cy="8" r="2.6" />
          <circle cx="10" cy="18" r="2.6" />
          <path d="M8.4 7l7-.6M7 8.3l2.2 7.2M16.4 10l-4.8 5.8" />
        </svg>
      );
    case 'search':
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="6.5" />
          <path d="M20 20l-4.4-4.4" />
        </svg>
      );
    case 'list':
      return (
        <svg {...common}>
          <path d="M9 6h11M9 12h11M9 18h11" />
          <path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" strokeWidth="2.6" />
        </svg>
      );
    case 'chat':
      return (
        <svg {...common}>
          <path d="M21 12a8 8 0 0 1-8 8H4l2.3-2.9A8 8 0 1 1 21 12z" />
        </svg>
      );
    case 'agent':
      return (
        <svg {...common}>
          <rect x="5" y="8" width="14" height="11" rx="2.5" />
          <path d="M12 8V4.5M9 13.5h.01M15 13.5h.01" strokeWidth="2.2" />
        </svg>
      );
    case 'sparkle':
      return (
        <svg {...common}>
          <path d="M12 3l1.9 5.7L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.3L12 3z" />
        </svg>
      );
    case 'pencil':
      return (
        <svg {...common}>
          <path d="M4 20l.9-3.6L16.4 4.9a2 2 0 0 1 2.8 0l0 0a2 2 0 0 1 0 2.8L7.6 19.1 4 20z" />
          <path d="M14.5 6.8l2.7 2.7" />
        </svg>
      );
    case 'file':
      return (
        <svg {...common}>
          <path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5L13.5 3z" />
          <path d="M13.5 3v5.5H19" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <rect x="4.5" y="4.5" width="15" height="15" rx="3" />
        </svg>
      );
  }
}

/** Icon for a step row, chosen from the step's kind/capability (shared with the trajectory view). */
export function StepTraceIcon({ step }: { step: TurnStep }) {
  return <TraceIcon name={iconForStep(step)} />;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`chat-trace__caret${open ? ' chat-trace__caret--open' : ''}`}
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/** Row duration = gap to the next step's ts; the running tail has no next yet. */
function stepSeconds(step: TurnStep, next?: TurnStep): number | null {
  if (!step.ts || !next?.ts) return null;
  const sec = Math.round(next.ts - step.ts);
  return sec >= 0 ? sec : null;
}

/** "思考 N 次 · 工具 M 次" for one group (parts with zero are dropped). */
function groupSummary(steps: TurnStep[], t: (k: string, o?: Record<string, unknown>) => string) {
  const think = steps.filter((s) => s.kind !== 'tool').length;
  const tools = steps.filter((s) => s.kind === 'tool').length;
  const parts: string[] = [];
  if (think > 0) parts.push(t('chat:trace.think', { n: think }));
  if (tools > 0) parts.push(t('chat:trace.tools', { n: tools }));
  return parts.join(' · ');
}

function StepRow({
  step,
  next,
  expanded,
  onToggle,
}: {
  step: TurnStep;
  next?: TurnStep;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation('chat');
  const label = step.kind === 'tool' ? toolLabel(step.name, t) : t('chat:proc.think');
  const dur = stepSeconds(step, next);
  return (
    <li className="chat-trace__row">
      <button
        type="button"
        className="chat-trace__rowbtn"
        aria-expanded={expanded}
        aria-label={`${label} ${t('chat:traj.detailToggle')}`}
        onClick={onToggle}
      >
        <span className="chat-trace__rowicon" aria-hidden>
          <TraceIcon name={iconForStep(step)} />
        </span>
        <span className="chat-trace__label">{label}</span>
        {step.summary ? (
          <span className="chat-trace__rowsummary" title={step.summary}>
            {step.summary}
          </span>
        ) : null}
        {dur !== null ? (
          <span className="chat-trace__dur">{formatDurationSec(dur, t)}</span>
        ) : null}
      </button>
      {expanded ? <StepDetail step={step} /> : null}
    </li>
  );
}

/** The step list of one group (rows stack over their fact sheets). */
function TraceStepList({ steps }: { steps: TurnStep[] }) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  return (
    <ul className="chat-trace__list">
      {steps.map((s, i) => (
        <StepRow
          key={s.seq}
          step={s}
          next={steps[i + 1]}
          expanded={!!expanded[s.seq]}
          onToggle={() => setExpanded((prev) => ({ ...prev, [s.seq]: !prev[s.seq] }))}
        />
      ))}
    </ul>
  );
}

/** One closed turn from the persisted trail: collapsed "已执行 N 步" summary,
 *  expandable to the full step list in place. */
export function ClosedTurnTrace({ steps }: { steps: TurnStep[] }) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const tools = steps.filter((s) => s.kind === 'tool').length;
  const first = steps[0]?.ts;
  const last = steps[steps.length - 1]?.ts;
  const totalSec = first && last ? Math.max(0, Math.round(last - first)) : 0;
  return (
    <div className="chat-trace">
      <button
        type="button"
        className="chat-trace__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Chevron open={open} />
        <span className="chat-trace__headtext">
          {t('chat:proc.done', { steps: steps.length, tools, dur: formatDurationSec(totalSec, t) })}
        </span>
      </button>
      {open ? <TraceStepList steps={steps} /> : null}
    </div>
  );
}

/** One live-turn segment: the round's frozen lead-in text above its step group. */
interface TraceSegment {
  key: string;
  /** Round number when the segment starts at an llm marker; leading steps
   *  (before any marker) form a headless segment with round=null. */
  round: number | null;
  text: string;
  steps: TurnStep[];
}

/** Split live steps into per-round groups: an llm marker starts its group and
 *  the tool steps after it belong to the same round (backend order: round
 *  deltas -> llm marker -> tool steps). Round text renders above its group. */
function buildSegments(steps: TurnStep[], roundTexts: RoundText[]): TraceSegment[] {
  const segments: TraceSegment[] = [];
  let current: TraceSegment | null = null;
  for (const s of steps) {
    if (s.kind !== 'tool') {
      current = { key: `r${s.round ?? s.seq}`, round: s.round ?? null, text: '', steps: [s] };
      segments.push(current);
    } else {
      if (!current) {
        current = { key: 'head', round: null, text: '', steps: [] };
        segments.push(current);
      }
      current.steps.push(s);
    }
  }
  for (const seg of segments) {
    if (seg.round !== null) {
      seg.text = roundTexts.find((r) => r.round === seg.round)?.text ?? '';
    }
  }
  return segments;
}

/** The live turn's inline trace — ONE stable collapsible unit sitting between
 *  the user's message and the final output. Position never moves: the block
 *  only grows downward inside a fixed-height, internally-scrolling body, so
 *  streaming output below is never pushed around. Auto behavior: expanded
 *  while tool steps stream in, collapsed to the summary line while output
 *  text flows; a header click pins the state until the turn ends. */
export function LiveTurnTrace() {
  const { t } = useTranslation('chat');
  const steps = useChatStore((s) => s.steps);
  const roundTexts = useChatStore((s) => s.roundTexts);
  const streaming = useChatStore((s) => s.streaming);
  const [manual, setManual] = useState<boolean | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const hadStepsRef = useRef(false);

  const running = steps.length > 0;
  // "Text is the latest activity": output yields the trace only while text
  // started flowing after the most recent step; the next tool step (or its
  // llm marker) flips activity back to the trace and it reopens. State, not
  // a ref, so the flip itself re-renders even when nothing else changed.
  const [textSinceStep, setTextSinceStep] = useState(false);
  useEffect(() => {
    setTextSinceStep(false);
  }, [steps.length]);
  useEffect(() => {
    if (streaming?.text) setTextSinceStep(true);
  }, [streaming?.text]);
  const autoOpen = running && !textSinceStep;
  const open = manual ?? autoOpen;

  // Reset the manual pin when the turn ends so the next turn starts fresh.
  useEffect(() => {
    if (hadStepsRef.current && steps.length === 0) setManual(null);
    hadStepsRef.current = steps.length > 0;
  }, [steps.length]);

  // Follow the action inside the fixed-height body only: the page layout
  // below (streaming output) is never scrolled or resized by trace growth.
  useEffect(() => {
    if (!open) return;
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [open, steps.length, streaming?.text]);

  if (!running) return null;
  const segments = buildSegments(steps, roundTexts);
  const summary = groupSummary(steps, t);

  return (
    <div className="chat-trace chat-trace--live">
      <button
        type="button"
        className="chat-trace__head"
        aria-expanded={open}
        onClick={() => setManual(!open)}
      >
        <Chevron open={open} />
        <span className="chat-trace__headtext">{summary}</span>
        {autoOpen ? (
          <span className="chat-trace__livebadge">
            <span className="chat-trace__pulse" aria-hidden />
            {t('chat:trace.working')}
          </span>
        ) : streaming?.text ? (
          <span className="chat-trace__livebadge">
            <span className="chat-trace__pulse" aria-hidden />
            {t('chat:trace.outputting')}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="chat-trace__body" ref={bodyRef}>
          {segments.map((seg) => (
            <Fragment key={seg.key}>
              {seg.text ? (
                <div className="chat-turntext chat-md">
                  <ChatMarkdown content={seg.text} />
                </div>
              ) : null}
              <TraceStepList steps={seg.steps} />
            </Fragment>
          ))}
        </div>
      ) : null}
    </div>
  );
}
