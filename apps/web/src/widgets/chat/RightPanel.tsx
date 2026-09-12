/**
 * @file RightPanel
 * @description Chat page side panel: the plan (agent todos + background task
 * cards) and the running subagents, mirroring an IDE-style progress sidebar.
 *
 * Data sources:
 * - Plan: agent.todo_read polled every 5s (workspace/todo.json, the same list
 *   the LLM's todo_write maintains) plus the live task.* progress cards from
 *   chatStore (rendered by TaskCards, passed in as children by the page)
 * - Agents: agent.list_subagents polled every 5s (no lifecycle SSE exists);
 *   clicking an entry interrupts that instance via the capability bridge
 */

import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { type TodoItem, listSubagents, listTodos } from '@/api/agent';
import { interruptInstance } from '@/bridge/chatSend';

/** A list_subagents.running entry (status is a RunStatus.value from agent/runtime/state.py). */
interface RunningInstance {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
}

const POLL_MS = 5000;

export function RightPanel({ taskCards }: { taskCards: ReactNode }) {
  const { t } = useTranslation('chat');
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [running, setRunning] = useState<RunningInstance[]>([]);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      listTodos()
        .then((r) => {
          if (alive) setTodos(r.items);
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

  return (
    <aside className="chat-side" aria-label={t('chat:panel.aria')}>
      <section className="chat-side__section">
        <h3 className="chat-side__title">{t('chat:panel.plan')}</h3>
        {todos.length > 0 ? (
          <ul className="chat-side__todos small">
            {todos.map((it, i) => (
              <li key={i} className={`chat-side__todo chat-side__todo--${it.status}`}>
                <span className="chat-side__mark" aria-hidden>
                  {it.status === 'done' ? '✓' : it.status === 'in_progress' ? '•' : '○'}
                </span>
                <span className="chat-side__content">{it.content}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="chat-side__empty small muted">{t('chat:panel.planEmpty')}</p>
        )}
        {taskCards}
      </section>
      <section className="chat-side__section">
        <h3 className="chat-side__title">{t('chat:panel.agents')}</h3>
        {running.length > 0 ? (
          <ul className="chat-side__agents small">
            {running.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className="chat-side__agent"
                  title={t('chat:panel.badgeTitle', { goal: r.goal, status: r.status })}
                  onClick={() => void interruptInstance(r.id)}
                >
                  <span className="chat-side__agent-name">{r.name}</span>
                  <span className="chat-side__agent-stop muted">{t('chat:composer.stop')}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="chat-side__empty small muted">{t('chat:panel.agentsEmpty')}</p>
        )}
      </section>
    </aside>
  );
}
