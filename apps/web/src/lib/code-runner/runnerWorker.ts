/**
 * @file runnerWorker
 * @description Creates the worker the fenced-code engines run in.
 *
 * The worker is loaded from a URL instead of a blob URL on purpose: a blob
 * worker inherits the page policy, while a worker loaded from a URL gets the
 * Content Security Policy of its own response. The engines compile snippets
 * (skulpt evaluates the compiled program, the JavaScript driver calls the
 * Function constructor), so that keeps the page policy free of 'unsafe-eval'.
 *
 * The engine driver travels to the worker as source and is installed by
 * public/code-runner-worker.js, which is the only script the worker needs.
 */

/** Worker script shipped with the app (public/code-runner-worker.js). */
export const RUNNER_WORKER_URL = '/code-runner-worker.js';

/**
 * Create a runner worker and install the engine driver into it.
 *
 * The driver is posted first: message order is preserved, so the driver is in
 * place before the engine receives its first run request.
 */
export function createRunnerWorker(driverSource: string): Worker {
  const worker = new Worker(RUNNER_WORKER_URL);
  worker.postMessage({ driver: driverSource });
  return worker;
}
