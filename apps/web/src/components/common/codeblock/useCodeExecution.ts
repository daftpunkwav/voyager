/**
 * @file useCodeExecution
 * @description Run lifecycle of one fenced snippet: start a run through the
 * code-runner registry, cancel it when the snippet changes or the block
 * unmounts, and drop the results of superseded runs.
 *
 * Responsibilities:
 * - Own the running/result state of a snippet
 * - Cancel the in-flight engine handle on a snippet change and on unmount
 * - Guard against the late result of a superseded run (generation counter)
 *
 * Constraints:
 * - Engine access stays behind the registry; this hook never reaches into a
 *   runner implementation.
 * - A settled result of an outdated run must never reach the UI.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getRunner, type ExecutionHandle, type ExecutionResult } from '@/lib/code-runner';

export interface CodeExecution {
  /** True while a run is in flight. */
  running: boolean;
  /** The settled outcome of the last run; null when there is none. */
  result: ExecutionResult | null;
  /** Start a run of the current snippet (no-op for non-runnable languages). */
  run: () => void;
  /** Cancel the in-flight run; the engine settles the run afterwards. */
  stop: () => void;
  /** Drop the settled result and close the output panel. */
  dismiss: () => void;
}

/** Run lifecycle of one fenced snippet. */
export function useCodeExecution(lang: string | null | undefined, text: string): CodeExecution {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const runRef = useRef<{ generation: number; handle: ExecutionHandle | null }>({
    generation: 0,
    handle: null,
  });

  // A new snippet resets prior execution state; stale runs are ignored.
  useEffect(() => {
    runRef.current.generation += 1;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    runRef.current.handle = null;
    setRunning(false);
    setResult(null);
  }, [text, lang]);

  // Abort in-flight runs on unmount (frees workers, drops late results).
  useEffect(
    () => () => {
      runRef.current.generation += 1;
      try {
        runRef.current.handle?.cancel();
      } catch {
        /* already settled */
      }
    },
    []
  );

  const run = useCallback(() => {
    const runner = getRunner(lang ?? undefined);
    if (!runner) return;
    const generation = runRef.current.generation + 1;
    runRef.current.generation = generation;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    setResult(null);
    setRunning(true);
    const handle = runner.run(text);
    runRef.current.handle = handle;
    void handle.done.then((outcome) => {
      if (runRef.current.generation !== generation) return;
      runRef.current.handle = null;
      setRunning(false);
      setResult(outcome);
    });
  }, [lang, text]);

  const stop = useCallback(() => {
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
  }, []);

  const dismiss = useCallback(() => setResult(null), []);

  return { running, result, run, stop, dismiss };
}
