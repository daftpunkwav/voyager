/**
 * @file RightPanel
 * @description Chat page side panel in three collapsible sections — plan,
 * agents, deliverables — mirroring a mainstream agent UI's progress sidebar.
 *
 * Data sources:
 * - Plan: agent.todo_read polled every 5s (workspace/todo.json, the same list
 *   the LLM's todo_write maintains) with a done/total counter
 * - Agents: agent.list_subagents polled every 5s (no lifecycle SSE exists);
 *   each row shows the elapsed runtime and interrupts that instance on click
 * - Deliverables: note artifacts from chatStore (note.created) plus the live
 *   task.* progress cards (rendered by TaskCards, passed in as children);
 *   the section stays visible with an empty hint when there is nothing to show
 */

import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { type TodoItem, listSubagents, listTodos } from '@/api/agent';
import { interruptInstance } from '@/bridge/chatSend';
import { routes } from '@/utils/routes';
import { formatDurationSec } from '@/utils/trajectory';
import { useChatStore } from '@/stores/chatStore';

/** A list_subagents.running entry (status is a RunStatus.value from agent/runtime/state.py). */
interface RunningInstance {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
}

const POLL_MS = 5000;

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
  // Ticks while subagents run so their elapsed time stays honest between polls.
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let alive = true;
    const pull = () => {
      listTodos()
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
              ((s.running as RunningInstance[]) ?? []).filter((r) => r.status === 'running')
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
  }, []);

  useEffect(() => {
    if (running.length === 0) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [running.length]);

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
        {running.length > 0 ? (
          <ul className="chat-side__agents">
            {running.map((r) => {
              const elapsed =
                r.started_ts > 0 ? Math.max(0, Math.round(now / 1000 - r.started_ts)) : null;
              return (
                <li key={r.id}>
                  <button
                    type="button"
                    className="chat-side__agent"
                    title={t('chat:panel.badgeTitle', { goal: r.goal, status: r.status })}
                    onClick={() => void interruptInstance(r.id)}
                  >
                    <span className="chat-side__pulse" aria-hidden />
                    <span className="chat-side__agentmain">
                      <span className="chat-side__agent-name">{r.name}</span>
                      {r.goal ? <span className="chat-side__agent-goal">{r.goal}</span> : null}
                    </span>
                    {elapsed !== null ? (
                      <span className="chat-side__agent-elapsed">
                        {formatDurationSec(elapsed, t)}
                      </span>
                    ) : null}
                    <span className="chat-side__agent-stop">{t('chat:composer.stop')}</span>
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
    </aside>
  );
}
