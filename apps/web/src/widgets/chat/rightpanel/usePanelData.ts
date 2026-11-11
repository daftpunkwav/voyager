/**
 * @file usePanelData
 * @description Polling behind the right panel: the open session's plan list
 * (agent.todowrite) and the running subagent instances (agent.list_subagents),
 * including the settled rows that briefly outlive their poll entry.
 *
 * Responsibilities:
 * - Poll the session plan and the running instances every 5s
 * - Filter the polled instances down to the open session
 * - Park a run that left the poll so a finished teammate does not vanish
 *   mid-glance, and mark it failed when its delivery failed
 * - Keep a per-second tick so the elapsed readouts stay honest between polls
 * - Keep the open execution view in sync with the polled instances
 *
 * Constraints:
 * - No rendering: the hooks only expose state, never markup.
 * - A failed poll is swallowed; the next round retries.
 */

import { useEffect, useRef, useState } from 'react';
import { type TodoItem, listSubagents, listTodos } from '@/api/agent';
import { useChatStore } from '@/stores/chatStore';
import type { RunningInstance } from '@/widgets/chat/rightpanel/runInstances';

const POLL_MS = 5000;

/** Settled runs park below the live ones so a finished teammate does not
 *  vanish mid-glance: clean endings linger briefly, failures longer; the park
 *  holds a bounded number either way. */
const SETTLED_KEEP_MS = 45_000;
const SETTLED_KEEP_FAILED_MS = 120_000;
const SETTLED_MAX = 12;

/** A run that left the poll, with the moment it was parked. */
interface SettledRow {
  row: RunningInstance;
  at: number;
}

/** Fold the runs that left the poll into the park: keep the entries still
 *  inside their window, add the newcomers, and drop the oldest overflow. */
function reconcileSettled(
  prev: SettledRow[],
  vanished: RunningInstance[],
  failedRunIds: Set<string>,
  nowMs: number
): SettledRow[] {
  const kept = prev.filter(
    ({ row, at }) =>
      nowMs - at < (row.status === 'failed' ? SETTLED_KEEP_FAILED_MS : SETTLED_KEEP_MS)
  );
  const keptIds = new Set(kept.map((k) => k.row.id));
  const additions = vanished
    .filter((r) => !keptIds.has(r.id))
    .map((r) => ({
      row: { ...r, status: failedRunIds.has(r.run_id ?? '') ? 'failed' : 'finished' },
      at: nowMs,
    }));
  // Nothing added and nothing expired: keep the previous array identity so
  // the 5s poll (which re-runs this effect via `running`) does not force a
  // redundant render pass on every tick.
  if (additions.length === 0 && kept.length === prev.length) return prev;
  return [...kept, ...additions].slice(-SETTLED_MAX);
}

/** The open session's plan: the todo list the agent maintains plus its
 *  done/total counter. */
export function usePlanTodos(): { todos: TodoItem[]; done: number; total: number } {
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [meta, setMeta] = useState({ done: 0, total: 0 });

  useEffect(() => {
    let alive = true;
    const pull = () => {
      listTodos(activeSessionId || undefined)
        .then((r) => {
          if (alive) {
            setTodos(r.items);
            setMeta({ done: r.done ?? 0, total: r.total ?? 0 });
          }
        })
        .catch(() => {}); // non-critical: a failed poll waits for the next round
    };
    pull();
    const timer = setInterval(pull, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [activeSessionId]);

  return { todos, done: meta.done, total: meta.total };
}

/** The running instances of the open session, the runs parked after they left
 *  the poll, and the execution view currently open (if any). */
export function useRunningAgents(): {
  running: RunningInstance[];
  settled: RunningInstance[];
  now: number;
  runView: RunningInstance | null;
  selectRun: (run: RunningInstance | null) => void;
  closeRun: () => void;
} {
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const [running, setRunning] = useState<RunningInstance[]>([]);
  // Ticks while subagents run so their elapsed time stays honest between polls.
  const [now, setNow] = useState(() => Date.now());
  // The subagent execution view (dialog) currently open, if any.
  const [runView, setRunView] = useState<RunningInstance | null>(null);
  // Runs that dropped out of the poll (terminal): kept briefly so a finished
  // teammate does not vanish mid-glance; failures stay a little longer.
  const [settled, setSettled] = useState<SettledRow[]>([]);

  useEffect(() => {
    let alive = true;
    const pull = () => {
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
      cur?.status === 'running' && !running.some((r) => r.id === cur.id)
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
        .deliveries.flatMap((d) => (d.status === 'failed' && d.run_id ? [d.run_id] : []))
    );
    const nowMs = Date.now();
    setSettled((prev) => reconcileSettled(prev, vanished, failedRuns, nowMs));
  }, [running, settled.length]);

  return {
    running,
    settled: settled.map((s) => s.row),
    now,
    runView,
    selectRun: (run: RunningInstance | null) => setRunView(run),
    closeRun: () => setRunView(null),
  };
}
