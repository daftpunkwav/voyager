/**
 * @file RightPanel
 * @description Chat page side panel in three collapsible sections — plan,
 * agents, deliverables — mirroring a mainstream agent UI's progress sidebar.
 *
 * Data sources:
 * - Plan: agent.todowrite (action=query) polled every 5s for the open session (the same
 *   per-session list the LLM's todo_write maintains) with a done/total counter
 * - Agents: agent.list_subagents polled every 5s (no lifecycle SSE exists),
 *   filtered to the open session; each row shows the elapsed runtime and
 *   opens the run's execution view on click (interrupt lives inside the view)
 * - Deliverables: note artifacts from chatStore (note.created) plus the live
 *   task.* progress cards (rendered by TaskCards, passed in as children);
 *   the section stays visible with an empty hint when there is nothing to show
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { type TodoItem, listSubagents, listTodos } from '@/api/agent';
import { SubagentRunDialog, type SubagentRunRef } from '@/widgets/chat/SubagentRunDialog';
import { routes } from '@/utils/routes';
import { formatDurationSec } from '@/utils/trajectory';
import { useChatStore } from '@/stores/chatStore';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { personaDisplayName } from '@/constants/personas';
import { AgentCharacterHead } from '@/components/agent/avatars/AgentCharacterHead';

/** A list_subagents.running entry (status is a RunStatus.value from agent/runtime/state.py).
 *  Extends the run dialog's SubagentRunRef contract instead of re-declaring the
 *  shared fields, so the two shapes cannot drift. */
interface RunningInstance extends SubagentRunRef {
  /** Chat session this run belongs to ('' = session-less / older backend). */
  session?: string;
}

const POLL_MS = 5000;

/** Settled runs park below the live ones so a finished teammate does not
 *  vanish mid-glance: clean endings linger briefly, failures longer; the park
 *  holds a bounded number either way. */
const SETTLED_KEEP_MS = 45_000;
const SETTLED_KEEP_FAILED_MS = 120_000;
const SETTLED_MAX = 12;

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`chat-side__chev${open ? ' chat-side__chev--open' : ''}`}
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

/** Collapsible panel section: title + trailing meta + chevron; children hidden when closed. */
function SideSection({
  title,
  meta,
  defaultOpen = true,
  children,
}: {
  title: string;
  meta?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="chat-side__section">
      <button
        type="button"
        className="chat-side__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Chevron open={open} />
        <span className="chat-side__title">{title}</span>
        {meta !== undefined && open ? <span className="chat-side__meta">{meta}</span> : null}
      </button>
      {open ? <div className="chat-side__body">{children}</div> : null}
    </section>
  );
}

function TodoMark({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <svg className="chat-side__mark chat-side__mark--done" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d="M8 12.5l2.7 2.7L16.5 9"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (status === 'in_progress') {
    return (
      <svg className="chat-side__mark chat-side__mark--doing" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d="M12 7.5A4.5 4.5 0 0 1 16.5 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg className="chat-side__mark" viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function RightPanel({ taskCards }: { taskCards: ReactNode }) {
  const { t } = useTranslation('chat');
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [todoMeta, setTodoMeta] = useState({ done: 0, total: 0 });
  const [running, setRunning] = useState<RunningInstance[]>([]);
  const artifacts = useChatStore((s) => s.artifacts);
  const cardCount = useChatStore((s) => s.cardOrder.length);
  // The panel mirrors the open session: plans and running instances are
  // per-session data (session-less rows ride along for older backends).
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  // Ticks while subagents run so their elapsed time stays honest between polls.
  const [now, setNow] = useState(() => Date.now());
  // The subagent execution view (dialog) currently open, if any.
  const [runView, setRunView] = useState<RunningInstance | null>(null);
  // Runs that dropped out of the poll (terminal): kept briefly so a finished
  // teammate does not vanish mid-glance; failures stay a little longer.
  const [settled, setSettled] = useState<Array<{ row: RunningInstance; at: number }>>([]);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      listTodos(activeSessionId || undefined)
        .then((r) => {
          if (alive) {
            setTodos(r.items);
            setTodoMeta({ done: r.done ?? 0, total: r.total ?? 0 });
          }
        })
        .catch(() => {}); // non-critical: a failed poll waits for the next round
      listSubagents()
        .then((s) => {
          if (alive)
            setRunning(
              ((s.running as RunningInstance[]) ?? []).filter(
                (r) => r.status === 'running' && (!r.session || r.session === activeSessionId)
              )
            );
        })
        .catch(() => {});
    };
    pull();
    const timer = setInterval(pull, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [activeSessionId]);

  useEffect(() => {
    if (running.length === 0) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [running.length]);

  // A finished run drops out of the polled list: sync the open dialog so it
  // stops ticking and offering Stop. The terminal status itself is not
  // observable through this poll, so it degrades to the neutral "finished".
  useEffect(() => {
    setRunView((cur) =>
      cur && cur.status === 'running' && !running.some((r) => r.id === cur.id)
        ? { ...cur, status: 'finished' }
        : cur
    );
  }, [running]);

  // Reconcile settled rows: a run that left the poll is parked here so a
  // finished teammate does not vanish mid-glance. The poll cannot see the
  // terminal status; a failed delivery card (agent.delivery) marks the row
  // failed, everything else degrades to the neutral finished. Failures linger
  // longer than clean endings; both are pruned past their keep window.
  const prevRunningRef = useRef<RunningInstance[]>([]);
  useEffect(() => {
    const prevList = prevRunningRef.current;
    prevRunningRef.current = running;
    const liveIds = new Set(running.map((r) => r.id));
    const vanished = prevList.filter((r) => !liveIds.has(r.id));
    if (vanished.length === 0 && settled.length === 0) return;
    const failedRuns = new Set(
      useChatStore
        .getState()
        .deliveries.filter((d) => d.status === 'failed' && d.run_id)
        .map((d) => d.run_id as string)
    );
    const nowMs = Date.now();
    setSettled((prev) => {
      const kept = prev.filter(
        ({ row, at }) =>
          nowMs - at < (row.status === 'failed' ? SETTLED_KEEP_FAILED_MS : SETTLED_KEEP_MS)
      );
      const keptIds = new Set(kept.map((k) => k.row.id));
      const additions = vanished
        .filter((r) => !keptIds.has(r.id))
        .map((r) => ({
          row: { ...r, status: failedRuns.has(r.run_id ?? '') ? 'failed' : 'finished' },
          at: nowMs,
        }));
      // Nothing added and nothing expired: keep the previous array identity so
      // the 5s poll (which re-runs this effect via `running`) does not force a
      // redundant render pass on every tick.
      if (additions.length === 0 && kept.length === prev.length) return prev;
      return [...kept, ...additions].slice(-SETTLED_MAX);
    });
  }, [running, settled.length]);

  const hasDeliverables = artifacts.length > 0 || cardCount > 0;

  return (
    <aside className="chat-side" aria-label={t('chat:panel.aria')}>
      <SideSection
        title={t('chat:panel.plan')}
        meta={todoMeta.total > 0 ? `${todoMeta.done}/${todoMeta.total}` : undefined}
      >
        {todos.length > 0 ? (
          <ul className="chat-side__todos">
            {todos.map((it, i) => (
              <li key={i} className={`chat-side__todo chat-side__todo--${it.status}`}>
                <TodoMark status={it.status} />
                <span className="chat-side__content">{it.content}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="chat-side__empty small muted">{t('chat:panel.planEmpty')}</p>
        )}
      </SideSection>
      <SideSection
        title={t('chat:panel.agents')}
        meta={running.length > 0 ? running.length : undefined}
      >
        {/* Resident team strip: every teammate is always on the roster; the
            status dot lights up while their persona has a live run. */}
        <div className="chat-side__team">
          {AGENT_CATALOG.filter((a) => a.id !== 'orchestrator').map((a) => {
            const busy = running.some(
              (r) => (r.persona ?? '') === a.id && (!r.session || r.session === activeSessionId)
            );
            return (
              <span
                key={a.id}
                className={`chat-side__member${busy ? ' chat-side__member--busy' : ''}`}
                title={`${personaDisplayName(a.id)} — ${busy ? t('chat:panel.memberBusy') : t('chat:panel.memberIdle')}`}
              >
                <span className="chat-side__member-avatar" aria-hidden>
                  <AgentCharacterHead agentId={a.id} look={{ x: 0, y: 0 }} isFocused={false} />
                </span>
                <span className="chat-side__member-name">{personaDisplayName(a.id)}</span>
                <span className="chat-side__member-dot" aria-hidden />
              </span>
            );
          })}
        </div>
        {running.length > 0 ? (
          <ul className="chat-side__agents">
            {[...running, ...settled.map((s) => s.row)].map((r) => {
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
                    onClick={() => setRunView(isMain ? null : r)}
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
                      <span className="chat-side__agent-elapsed">
                        {formatDurationSec(elapsed, t)}
                      </span>
                    ) : null}
                    <span className="chat-side__agent-stop">{t('chat:panel.viewRun')}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="chat-side__empty small muted">{t('chat:panel.agentsEmpty')}</p>
        )}
      </SideSection>
      <SideSection
        title={t('chat:panel.deliverables')}
        meta={hasDeliverables ? artifacts.length + cardCount : undefined}
      >
        {artifacts.length > 0 ? (
          <ul className="chat-side__artifacts">
            {artifacts.map((a) => (
              <li key={a.seq}>
                <Link to={routes.note(a.noteId)} className="chat-side__artifact" title={a.title}>
                  <svg className="chat-side__artifact-icon" viewBox="0 0 24 24" aria-hidden>
                    <path
                      d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5L13.5 3z"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.9"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M13.5 3v5.5H19"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.9"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span className="chat-side__artifact-title">{a.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
        {taskCards}
        {!hasDeliverables ? (
          <p className="chat-side__empty small muted">{t('chat:panel.deliverablesEmpty')}</p>
        ) : null}
      </SideSection>
      <SubagentRunDialog
        instance={runView}
        open={runView !== null}
        onClose={() => setRunView(null)}
      />
    </aside>
  );
}
