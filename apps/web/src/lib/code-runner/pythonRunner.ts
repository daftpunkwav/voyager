/**
 * @file Python snippet execution via skulpt (in-browser interpreter).
 * skulpt ships only as classic scripts, so the engine loads from the vendored
 * copies under public/vendor/skulpt (pinned skulpt 1.2.0, no CDN, works
 * offline). The engine runs inside the code-runner worker, which is served as
 * its own script: skulpt evaluates the compiled program, so the worker policy
 * is what has to allow that, not the page policy. Runs are serialized because
 * Sk.configure targets global state inside the worker; CPU abuse is bounded by
 * execLimit (raises TimeLimitError). Subset limits (no third-party packages,
 * no file/network access) are inherent to skulpt and surface as ordinary
 * runtime errors.
 *
 * Vendored files: https://github.com/skulpt/skulpt (skulpt.min.js +
 * skulpt-stdlib.js, release 1.2.0, MIT license — unmodified upstream builds).
 */

import { truncateText } from './output';
import { createRunnerWorker } from './runnerWorker';
import {
  DEFAULT_MAX_OUTPUT_CHARS,
  DEFAULT_TIMEOUT_MS,
  type ExecutionHandle,
  type ExecutionResult,
} from './types';

/** Error shape the worker reports back; skulpt errors are plain objects. */
interface PythonWorkerError {
  tp$name?: unknown;
  args?: { v?: { v?: unknown }[] };
  name?: unknown;
  message?: unknown;
}

const VENDOR_BASE = '/vendor/skulpt';

/** Cached worker promise: the engine loads once inside the worker. */
let workerPromise: Promise<Worker> | null = null;

/** Serialized tail: skulpt output capture is global in the worker, so runs queue up. */
let runTail: Promise<unknown> = Promise.resolve();

/**
 * Worker-side Python driver.
 *
 * Installed into the runner worker as source: the worker loads the vendored
 * engine with importScripts (synchronous in a worker), captures the output and
 * reports the result. Kept self-contained because it ships as text.
 */
export function buildPythonWorkerSource(): string {
  return `
var engine = null;
function loadEngine() {
  if (engine) return engine;
  importScripts('${VENDOR_BASE}/skulpt.min.js');
  importScripts('${VENDOR_BASE}/skulpt-stdlib.js');
  engine = self.Sk;
  if (!engine || !engine.misceval || typeof engine.importMainWithBody !== 'function') {
    throw new Error('Skulpt engine failed to initialize.');
  }
  return engine;
}
self.onmessage = async function (event) {
  var data = event.data || {};
  var source = typeof data.source === 'string' ? data.source : '';
  var limit = typeof data.maxOutputChars === 'number' ? data.maxOutputChars : 0;
  var budget = typeof data.timeoutMs === 'number' ? data.timeoutMs : 0;
  var captured = '';
  try {
    var skulpt = loadEngine();
    skulpt.configure({
      output: function (text) {
        captured += text;
        if (limit > 0 && captured.length > limit + 1024) captured = captured.slice(0, limit + 1024);
      },
      read: function (filename) {
        var files = skulpt.builtinFiles && skulpt.builtinFiles.files;
        if (!files || !(filename in files)) {
          throw new Error('Module not available in the browser sandbox: ' + filename);
        }
        return files[filename];
      },
      execLimit: budget,
      __future__: skulpt.python3
    });
    await skulpt.misceval.asyncToPromise(function () {
      return skulpt.importMainWithBody('<stdin>', false, source, true);
    });
    self.postMessage({ ok: true, output: captured });
  } catch (err) {
    self.postMessage({ ok: false, output: captured, error: err });
  }
};
`;
}

/** Load the runner worker once; rejects when it cannot be started. */
function loadWorker(): Promise<Worker> {
  workerPromise ??= Promise.resolve()
    .then(() => {
      const worker = createRunnerWorker(buildPythonWorkerSource());
      // A worker that dies cannot serve later runs; drop it so the next run starts fresh.
      worker.addEventListener('error', () => {
        workerPromise = null;
        try {
          worker.terminate();
        } catch {
          /* already gone */
        }
      });
      return worker;
    })
    .catch((err: unknown) => {
      // Allow a later retry after transient failures.
      workerPromise = null;
      throw err;
    });
  return workerPromise;
}

/** Best-effort "Type: detail" from the many shapes skulpt errors take. */
export function formatSkulptError(err: unknown): string {
  if (err === null || err === undefined) return 'Unknown error';
  try {
    const record = err as {
      tp$name?: unknown;
      args?: { v?: { v?: unknown }[] };
      message?: unknown;
    };
    const name =
      typeof record.tp$name === 'string' && record.tp$name
        ? record.tp$name
        : err instanceof Error
          ? err.name
          : 'Error';
    const firstArg = record.args?.v?.[0]?.v;
    const detail =
      typeof firstArg === 'string' && firstArg
        ? firstArg
        : typeof record.message === 'string' && record.message
          ? record.message
          : '';
    return detail ? `${name}: ${detail}` : name;
  } catch {
    return 'Unknown error';
  }
}

/** One run in the worker: the captured output plus the error, if any. */
interface PythonRunOutcome {
  output: string;
  error?: PythonWorkerError;
}

/** Post one run to the worker and wait for its report. */
function runInWorker(
  worker: Worker,
  source: string,
  timeoutMs: number,
  maxChars: number
): Promise<PythonRunOutcome> {
  return new Promise((resolve) => {
    const onMessage = (event: MessageEvent) => {
      cleanup();
      const data = (event.data ?? {}) as {
        output?: unknown;
        error?: unknown;
      };
      resolve({
        output: typeof data.output === 'string' ? data.output : '',
        error: data.error as PythonWorkerError | undefined,
      });
    };
    const onError = (event: ErrorEvent) => {
      cleanup();
      resolve({
        output: '',
        error: { name: 'Error', message: event.message || 'The Python worker failed.' },
      });
    };
    const cleanup = () => {
      worker.removeEventListener('message', onMessage);
      worker.removeEventListener('error', onError);
    };
    worker.addEventListener('message', onMessage);
    worker.addEventListener('error', onError);
    worker.postMessage({ source, timeoutMs, maxOutputChars: maxChars });
  });
}

/** Execute Python source with the vendored skulpt engine. SSR-safe. */
export function runPython(
  source: string,
  limits?: { timeoutMs?: number; maxOutputChars?: number }
): ExecutionHandle {
  const timeoutMs = Math.max(1000, limits?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const maxChars = limits?.maxOutputChars ?? DEFAULT_MAX_OUTPUT_CHARS;
  if (!source.trim()) {
    return {
      done: Promise.resolve({
        status: 'ok',
        output: '',
        durationMs: 0,
        truncated: false,
      }),
      cancel: () => undefined,
    };
  }

  let cancelled = false;
  const startedAt = Date.now();
  const settleResult = (partial: {
    status: ExecutionResult['status'];
    output: string;
    error?: string;
  }): ExecutionResult => {
    const out = truncateText(partial.output, maxChars);
    return {
      status: cancelled && partial.status !== 'unavailable' ? 'cancelled' : partial.status,
      output: out.text,
      error: partial.error,
      durationMs: Date.now() - startedAt,
      truncated: out.truncated,
    };
  };

  const run = (async (): Promise<ExecutionResult> => {
    // Serialize against earlier runs: Sk.configure output capture is global in the worker.
    await runTail.catch(() => {});
    if (cancelled) {
      return settleResult({ status: 'cancelled', output: '' });
    }
    let worker: Worker;
    try {
      worker = await loadWorker();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return settleResult({
        status: 'unavailable',
        output: '',
        error: `Python runner unavailable: ${message}`,
      });
    }
    if (cancelled) {
      return settleResult({ status: 'cancelled', output: '' });
    }

    const outcome = await runInWorker(worker, source, timeoutMs, maxChars);
    if (!outcome.error) {
      return settleResult({ status: 'ok', output: outcome.output });
    }
    const message = formatSkulptError(outcome.error);
    const timedOut =
      outcome.error.tp$name === 'TimeLimitError' || /TimeLimit|timed out/i.test(message);
    return settleResult({
      status: timedOut ? 'timeout' : 'error',
      output: outcome.output,
      error: message,
    });
  })();
  runTail = run.catch(() => {});

  return {
    done: run,
    cancel() {
      // skulpt cannot be preempted mid-run; execLimit bounds the overrun and
      // the outcome is reported as cancelled once the engine settles.
      cancelled = true;
    },
  };
}
