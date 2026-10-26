/**
 * @file workerHarness
 * @description Simulated worker scope for the fenced-code runner tests.
 *
 * The runner has two halves: the page-side drivers (javascriptRunner.ts,
 * pythonRunner.ts) and the worker bootstrap the app ships
 * (public/code-runner-worker.js). The bootstrap installs the driver the page
 * sends and holds the runner to the page origin, so the tests run that file
 * itself instead of a stand-in: the harness hands it a worker global scope
 * whose `self` is the global object and whose `importScripts` evaluates
 * scripts in that scope, the way a browser worker does.
 *
 * The scope is a V8 context, so the bootstrap, the driver and the vendored
 * engine share one global. A broken bootstrap therefore fails the tests
 * instead of passing behind a stand-in that installs the driver itself.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { vi } from 'vitest';

/** Host the simulated worker is served from. */
const WORKER_HOST = 'localhost:5173';

/** Origin the simulated worker is served from. */
const WORKER_ORIGIN = `http://${WORKER_HOST}`;

/** WebSocket origin of the same host, the way a snippet reaches it. */
export const WORKER_WS_ORIGIN = `ws://${WORKER_HOST}`;

/** Location of the simulated worker script. */
const WORKER_LOCATION = `${WORKER_ORIGIN}/code-runner-worker.js`;

/** Vendored engine script the Python driver imports inside the worker. */
export const SKULPT_ENGINE_URL = '/vendor/skulpt/skulpt.min.js';

/** Vendored standard library the Python driver imports inside the worker. */
export const SKULPT_STDLIB_URL = '/vendor/skulpt/skulpt-stdlib.js';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** Makes the context global its own `self`, the way a worker global is. */
const WORKER_GLOBAL_SETUP = 'globalThis.self = globalThis;';

/** The bootstrap the app ships, read from the file that is served. */
const BOOTSTRAP_SOURCE = readFileSync(
  path.join(appRoot, 'public', 'code-runner-worker.js'),
  'utf8'
);

/** Socket constructor as the bootstrap leaves it. */
export interface SocketConstructor {
  (url: string, protocols?: string | string[]): unknown;
  CONNECTING?: number;
  OPEN?: number;
  CLOSING?: number;
  CLOSED?: number;
  prototype: { constructor: unknown };
}

/** The worker global scope the bootstrap and the driver run in. */
export interface WorkerScope {
  /** Worker location, as a worker global carries it. */
  location: { href: string; origin: string; protocol: string; host: string };
  /** URL constructor that hands out blob URLs of the worker origin. */
  URL: typeof URL;
  /** Blob constructor that carries the driver source. */
  Blob: new (parts: string[]) => { text(): string };
  /** Guarded fetch: cross-origin targets are refused. */
  fetch: (input: unknown) => Promise<unknown>;
  /** Guarded XMLHttpRequest: its open refuses cross-origin targets. */
  XMLHttpRequest: { prototype: { open(method: string, url: string): void } };
  /** Guarded WebSocket constructor. */
  WebSocket: SocketConstructor;
  /** Guarded EventSource constructor. */
  EventSource: SocketConstructor;
  /** Guarded importScripts: cross-origin targets are refused. */
  importScripts: (url: string) => void;
  /** Message handler the bootstrap and then the driver install. */
  onmessage: ((event: { data: unknown }) => unknown) | null;
  /** Reports the worker sends back to the page. */
  postMessage: (report: unknown) => void;
  /** The engine the vendored script defines, once it has been imported. */
  Sk?: unknown;
  [key: string]: unknown;
}

/** Options for a simulated worker. */
export interface WorkerHarnessOptions {
  /**
   * Engine the vendored skulpt script defines. The harness installs it on the
   * worker scope when the driver imports that script, the way the vendored
   * file does; it is absent before the import.
   */
  engine?: unknown;
}

/** A simulated worker scope with the shipped bootstrap already installed. */
export interface WorkerHarness {
  /** The worker global scope the bootstrap and the driver run in. */
  readonly scope: WorkerScope;
  /** Messages the worker posted back to the page. */
  readonly reports: unknown[];
  /** Scripts the worker was asked to import, in order. */
  readonly imports: string[];
  /** Requests the worker was allowed to make. */
  readonly fetches: string[];
  /** Requests the worker opened over XMLHttpRequest. */
  readonly xhrOpens: string[];
  /** Socket URLs the worker connected to. */
  readonly socketUrls: string[];
  /** Event stream URLs the worker subscribed to. */
  readonly eventSourceUrls: string[];
  /** Called for every message the worker posts back to the page. */
  onReport: (report: unknown) => void;
  /** Hand a page message to the worker and wait for its handler to settle. */
  deliver(message: unknown): Promise<void>;
}

/** The URL a request target points at. */
function targetUrl(target: unknown): string {
  if (typeof target === 'string') return target;
  const url = (target as { url?: unknown } | null | undefined)?.url;
  return typeof url === 'string' ? url : String(target);
}

/**
 * Create a worker scope with the shipped bootstrap installed.
 *
 * The bootstrap runs against a scope that carries the platform APIs it
 * replaces, so its guards are exercised for real.
 */
export function createWorkerHarness(options: WorkerHarnessOptions = {}): WorkerHarness {
  const reports: unknown[] = [];
  const imports: string[] = [];
  const fetches: string[] = [];
  const xhrOpens: string[] = [];
  const socketUrls: string[] = [];
  const eventSourceUrls: string[] = [];
  /** Driver sources handed out as blob URLs, keyed by the URL. */
  const driverSources = new Map<string, string>();
  let driverCounter = 0;
  let onReport: (report: unknown) => void = () => {};

  /** Blob stand-in: the bootstrap only needs the text the driver carries. */
  class HarnessBlob {
    readonly parts: string[];
    constructor(parts: string[]) {
      this.parts = parts;
    }
    text(): string {
      return this.parts.join('');
    }
  }

  /** URL stand-in: the platform URL plus blob URLs of the worker origin. */
  class HarnessUrl extends URL {
    static override createObjectURL(blob: Blob): string {
      const url = `blob:${WORKER_ORIGIN}/__driver__${++driverCounter}`;
      driverSources.set(url, (blob as unknown as HarnessBlob).text());
      return url;
    }
    static override revokeObjectURL(url: string): void {
      driverSources.delete(url);
    }
  }

  /** XMLHttpRequest stand-in: the bootstrap guards its open method. */
  class HarnessXhr {
    open(_method: string, url: string): void {
      xhrOpens.push(url);
    }
  }

  /** WebSocket stand-in: the bootstrap guards its constructor. */
  class HarnessWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readonly url: string;
    constructor(url: string) {
      this.url = url;
      socketUrls.push(url);
    }
  }

  /** EventSource stand-in: the bootstrap guards its constructor. */
  class HarnessEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readonly url: string;
    constructor(url: string) {
      this.url = url;
      eventSourceUrls.push(url);
    }
  }

  const scope = {
    console,
    location: {
      href: WORKER_LOCATION,
      origin: WORKER_ORIGIN,
      protocol: 'http:',
      host: WORKER_HOST,
    },
    URL: HarnessUrl,
    Blob: HarnessBlob,
    fetch: (input: unknown): Promise<unknown> => {
      fetches.push(targetUrl(input));
      return Promise.resolve({ ok: true, status: 200 });
    },
    XMLHttpRequest: HarnessXhr,
    WebSocket: HarnessWebSocket,
    EventSource: HarnessEventSource,
    postMessage: (report: unknown): void => {
      reports.push(report);
      onReport(report);
    },
  } as unknown as WorkerScope;

  const context = vm.createContext(scope);
  scope.importScripts = (url: string): void => {
    imports.push(url);
    const source = driverSources.get(url);
    if (source !== undefined) {
      // The driver is the app's own generated source, never user input.
      vm.runInContext(source, context); // NOSONAR
      return;
    }
    if (url === SKULPT_ENGINE_URL) {
      // The vendored script defines the engine on the worker scope.
      scope.Sk = options.engine;
      return;
    }
    if (url === SKULPT_STDLIB_URL) {
      // The standard library only extends the engine the first script defined.
      return;
    }
    throw new Error(`Unexpected importScripts target: ${url}`);
  };

  // A worker global is its own `self`, and the scripts it imports run in it.
  // The evaluated source is the app's own shipped file, never user input.
  vm.runInContext(`${WORKER_GLOBAL_SETUP}\n${BOOTSTRAP_SOURCE}`, context); // NOSONAR

  return {
    scope,
    reports,
    imports,
    fetches,
    xhrOpens,
    socketUrls,
    eventSourceUrls,
    get onReport(): (report: unknown) => void {
      return onReport;
    },
    set onReport(handler: (report: unknown) => void) {
      onReport = handler;
    },
    async deliver(message: unknown): Promise<void> {
      const handler = scope.onmessage;
      if (typeof handler !== 'function') {
        throw new Error('The worker has no message handler.');
      }
      await handler({ data: message });
    },
  };
}

/** A worker the page created, as the runner sees it. */
export interface FakeWorkerHandle {
  /** Script URLs the page asked the workers to load. */
  readonly urls: string[];
  /** The scope behind every worker that was created. */
  readonly harnesses: WorkerHarness[];
}

/**
 * Stand in for the Worker the runners create: it loads the shipped bootstrap
 * and installs the driver the page sends, so the runner paths run against the
 * code the browser runs.
 */
export function installFakeWorker(options: WorkerHarnessOptions = {}): FakeWorkerHandle {
  const urls: string[] = [];
  const harnesses: WorkerHarness[] = [];

  class FakeWorker {
    onmessage: ((event: { data: unknown }) => void) | null = null;
    onerror: ((event: { message: string }) => void) | null = null;
    private readonly harness: WorkerHarness;
    private readonly listeners = new Map<string, Set<(event: unknown) => void>>();

    constructor(url: string) {
      urls.push(url);
      this.harness = createWorkerHarness(options);
      harnesses.push(this.harness);
      this.harness.onReport = (report: unknown) => {
        this.onmessage?.({ data: report });
        this.emit('message', { data: report });
      };
    }

    addEventListener(type: string, listener: (event: unknown) => void): void {
      const set = this.listeners.get(type) ?? new Set();
      set.add(listener);
      this.listeners.set(type, set);
    }

    removeEventListener(type: string, listener: (event: unknown) => void): void {
      this.listeners.get(type)?.delete(listener);
    }

    private emit(type: string, event: unknown): void {
      for (const listener of this.listeners.get(type) ?? []) listener(event);
    }

    postMessage(message: unknown): void {
      void this.harness.deliver(message).catch((err: unknown) => {
        this.onerror?.({ message: err instanceof Error ? err.message : String(err) });
      });
    }

    terminate(): void {}
  }

  vi.stubGlobal('Worker', FakeWorker);
  return { urls, harnesses };
}
