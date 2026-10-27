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
 *
 * The platform APIs sit on the prototype of the global, the way a browser
 * worker carries them: the bootstrap has to take them away from the prototype
 * as well as from the global, and the tests reach them through the same
 * prototype chain the snippet would use. They resolve a URL argument the way
 * the native API does (string conversion, then the worker URL as the base), so
 * a test that hands one a target the native would read differently shows up as
 * the URL the native would use.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { vi } from 'vitest';

/** Host the simulated worker is served from. */
const WORKER_HOST = 'localhost:5173';

/** Origin the simulated worker is served from, for the page scheme in use. */
export function workerOrigin(secure: boolean): string {
  return `${secure ? 'https' : 'http'}://${WORKER_HOST}`;
}

/** Origin the simulated worker is served from. */
export const WORKER_ORIGIN = workerOrigin(false);

/** WebSocket origin of the same host, the way a snippet reaches it. */
export const WORKER_WS_ORIGIN = `ws://${WORKER_HOST}`;

/** Vendored engine script the Python driver imports inside the worker. */
export const SKULPT_ENGINE_URL = '/vendor/skulpt/skulpt.min.js';

/** Vendored standard library the Python driver imports inside the worker. */
export const SKULPT_STDLIB_URL = '/vendor/skulpt/skulpt-stdlib.js';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** Makes the context global its own `self`, the way a worker global is. */
const WORKER_GLOBAL_SETUP = 'globalThis.self = globalThis;';

/**
 * Puts the platform APIs on the prototype of the global, the way a browser
 * worker carries them, and hands that prototype back.
 */
const WORKER_GLOBAL_SCOPE = `
  var workerGlobalScope = Object.create(Object.prototype);
  Object.setPrototypeOf(globalThis, workerGlobalScope);
  workerGlobalScope;
`;

/** The bootstrap the app ships, read from the file that is served. */
const BOOTSTRAP_SOURCE = readFileSync(
  path.join(appRoot, 'public', 'code-runner-worker.js'),
  'utf8'
);

/** Absolute URL of a worker-relative path, as the native APIs resolve it. */
export function workerUrl(path: string, secure = false): string {
  return new URL(path, `${workerOrigin(secure)}/code-runner-worker.js`).href;
}

/** Socket constructor as the bootstrap leaves it. */
export interface SocketConstructor {
  (url: unknown, protocols?: string | string[]): unknown;
  CONNECTING?: number;
  OPEN?: number;
  CLOSING?: number;
  CLOSED?: number;
  prototype: { constructor: unknown };
}

/** A request the worker was allowed to make. */
export interface WorkerFetch {
  /** The URL the native fetch would send the request to. */
  url: string;
  /** The redirect mode the guarded fetch fixed on the request. */
  redirect: string;
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
  fetch: (input: unknown, init?: unknown) => Promise<unknown>;
  /** Guarded XMLHttpRequest: its open refuses cross-origin targets. */
  XMLHttpRequest: { prototype: { open(method: string, url: unknown): void } };
  /** Guarded WebSocket constructor. */
  WebSocket: SocketConstructor;
  /** Guarded EventSource constructor. */
  EventSource: SocketConstructor;
  /** Guarded WebTransport constructor. */
  WebTransport: SocketConstructor;
  /** Guarded importScripts: cross-origin targets are refused. */
  importScripts: (...urls: unknown[]) => void;
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
  /**
   * Serve the worker from a secure origin. A WebTransport needs a secure
   * context, so the guard for it is only observable there.
   */
  secure?: boolean;
}

/** A simulated worker scope with the shipped bootstrap already installed. */
export interface WorkerHarness {
  /** The worker global scope the bootstrap and the driver run in. */
  readonly scope: WorkerScope;
  /** The prototype the platform APIs sit on, the way a worker carries them. */
  readonly prototype: Record<string, unknown>;
  /** Messages the worker posted back to the page. */
  readonly reports: unknown[];
  /** Scripts the worker was asked to import, in order. */
  readonly imports: string[];
  /** Requests the worker was allowed to make. */
  readonly fetches: WorkerFetch[];
  /** Requests the worker opened over XMLHttpRequest. */
  readonly xhrOpens: string[];
  /** Socket URLs the worker connected to. */
  readonly socketUrls: string[];
  /** Event stream URLs the worker subscribed to. */
  readonly eventSourceUrls: string[];
  /** Transport URLs the worker connected to. */
  readonly transportUrls: string[];
  /** Called for every message the worker posts back to the page. */
  onReport: (report: unknown) => void;
  /** Hand a page message to the worker and wait for its handler to settle. */
  deliver(message: unknown): Promise<void>;
  /** Run an expression in the worker scope, the way a snippet sees it. */
  evaluate(expression: string): unknown;
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
  const fetches: WorkerFetch[] = [];
  const xhrOpens: string[] = [];
  const socketUrls: string[] = [];
  const eventSourceUrls: string[] = [];
  const transportUrls: string[] = [];
  /** Driver sources handed out as blob URLs, keyed by the URL. */
  const driverSources = new Map<string, string>();
  let driverCounter = 0;
  let onReport: (report: unknown) => void = () => {};
  const origin = workerOrigin(options.secure ?? false);
  const protocol = options.secure ? 'https:' : 'http:';
  const location = `${origin}/code-runner-worker.js`;
  const engineUrl = new URL(SKULPT_ENGINE_URL, location).href;
  const stdlibUrl = new URL(SKULPT_STDLIB_URL, location).href;

  /**
   * The URL a native API resolves the target to: string conversion, then the
   * worker URL as the base.
   */
  const resolveUrl = (target: unknown): string => new URL(String(target), location).href;

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
      const url = `blob:${origin}/__driver__${++driverCounter}`;
      driverSources.set(url, (blob as unknown as HarnessBlob).text());
      return url;
    }
    static override revokeObjectURL(url: string): void {
      driverSources.delete(url);
    }
  }

  /**
   * Request stand-in: the guarded fetch builds one and the native fetch reads
   * its URL, so the harness carries the same accessor on the prototype.
   */
  class HarnessRequest {
    private readonly requestUrl: string;
    readonly redirect: string;
    constructor(input: unknown, init: { redirect?: string } = {}) {
      if (input instanceof HarnessRequest) {
        this.requestUrl = input.url;
        this.redirect = init.redirect ?? input.redirect;
      } else {
        this.requestUrl = resolveUrl(input);
        this.redirect = init.redirect ?? 'follow';
      }
    }
    /** The URL the native Request exposes through its prototype accessor. */
    get url(): string {
      return this.requestUrl;
    }
  }

  /** XMLHttpRequest stand-in: the bootstrap guards its open method. */
  class HarnessXhr {
    open(_method: string, url: unknown): void {
      xhrOpens.push(resolveUrl(url));
    }
  }

  /** WebSocket stand-in: the bootstrap guards its constructor. */
  class HarnessWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readonly url: string;
    constructor(url: unknown) {
      this.url = resolveUrl(url);
      socketUrls.push(this.url);
    }
  }

  /** EventSource stand-in: the bootstrap guards its constructor. */
  class HarnessEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readonly url: string;
    constructor(url: unknown) {
      this.url = resolveUrl(url);
      eventSourceUrls.push(this.url);
    }
  }

  /** WebTransport stand-in: the bootstrap guards its constructor. */
  class HarnessWebTransport {
    readonly url: string;
    constructor(url: unknown) {
      this.url = resolveUrl(url);
      transportUrls.push(this.url);
    }
  }

  /** Nested worker stand-in: the bootstrap takes it away from the snippet. */
  class HarnessNestedWorker {
    constructor(url: unknown) {
      transportUrls.push(resolveUrl(url));
    }
  }

  const scope = {
    console,
    location: {
      href: location,
      origin,
      protocol,
      host: WORKER_HOST,
    },
    Blob: HarnessBlob,
    postMessage: (report: unknown): void => {
      reports.push(report);
      onReport(report);
    },
  } as unknown as WorkerScope;

  const context = vm.createContext(scope);

  // The platform APIs live on the prototype of the global, the way a browser
  // worker carries them: the bootstrap has to take them away from there too.
  // The scope setup is the harness's own code, never user input.
  const scopeSetup = vm.runInContext(WORKER_GLOBAL_SCOPE, context); // NOSONAR
  const workerGlobalScope = scopeSetup as Record<string, unknown>;
  workerGlobalScope.URL = HarnessUrl;
  workerGlobalScope.Request = HarnessRequest;
  workerGlobalScope.fetch = (input: unknown, init?: { redirect?: string }): Promise<unknown> => {
    const request = new HarnessRequest(input, init ?? {});
    fetches.push({ url: request.url, redirect: request.redirect });
    return Promise.resolve({ ok: true, status: 200 });
  };
  workerGlobalScope.XMLHttpRequest = HarnessXhr;
  workerGlobalScope.WebSocket = HarnessWebSocket;
  workerGlobalScope.EventSource = HarnessEventSource;
  workerGlobalScope.WebTransport = HarnessWebTransport;
  workerGlobalScope.Worker = HarnessNestedWorker;
  workerGlobalScope.importScripts = (...urls: unknown[]): void => {
    for (const target of urls) {
      const url = resolveUrl(target);
      imports.push(url);
      const source = driverSources.get(url);
      if (source !== undefined) {
        // The driver is the app's own generated source, never user input.
        vm.runInContext(source, context); // NOSONAR
        continue;
      }
      if (url === engineUrl) {
        // The vendored script defines the engine on the worker scope.
        scope.Sk = options.engine;
        continue;
      }
      if (url === stdlibUrl) {
        // The standard library only extends the engine the first script defined.
        continue;
      }
      throw new Error(`Unexpected importScripts target: ${url}`);
    }
  };

  // A worker global is its own `self`, and the scripts it imports run in it.
  // The evaluated source is the app's own shipped file, never user input.
  vm.runInContext(`${WORKER_GLOBAL_SETUP}\n${BOOTSTRAP_SOURCE}`, context); // NOSONAR

  return {
    scope,
    prototype: workerGlobalScope,
    reports,
    imports,
    fetches,
    xhrOpens,
    socketUrls,
    eventSourceUrls,
    transportUrls,
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
    evaluate(expression: string): unknown {
      // The expression comes from a test, never from user input.
      return vm.runInContext(expression, context); // NOSONAR
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
    onmessage: ((event: { data: unknown }) => unknown) | null = null;
    onerror: ((event: { message: string }) => unknown) | null = null;
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
