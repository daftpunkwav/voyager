/**
 * @file codeRunnerWorker
 * @description Unit coverage for the worker bootstrap the app ships
 * (public/code-runner-worker.js).
 *
 * The bootstrap installs the engine driver the page sends and holds the runner
 * to the page origin, so the tests run that file in a simulated worker scope:
 * a broken message handler or a missing origin guard has to fail them.
 *
 * The snippet shares the worker global, so the guards have to survive a
 * snippet that tries to take them away. The tests reach the platform APIs
 * through the same prototype chain a snippet would use.
 */

import { describe, expect, it } from 'vitest';
import {
  createWorkerHarness,
  SKULPT_ENGINE_URL,
  SKULPT_STDLIB_URL,
  WORKER_ORIGIN,
  WORKER_WS_ORIGIN,
  workerOrigin,
} from './helpers/workerHarness';

/** Minimal driver: the bootstrap only has to install and run what the page sends. */
const DRIVER_STUB = `self.onmessage = function (event) {
  self.postMessage({ ok: true, driver: 'installed' });
};`;

/** The worker global, as a snippet sees it. */
type SnippetScope = Record<string, unknown>;

describe('worker bootstrap', () => {
  it('installs the driver the page sends and runs it', async () => {
    const harness = createWorkerHarness();
    await harness.deliver({ driver: DRIVER_STUB });
    await harness.deliver({ source: 'ignored by the stub' });
    expect(harness.reports[0]).toMatchObject({ ok: true, driver: 'installed' });
  });

  it('refuses a message that carries no driver', async () => {
    const harness = createWorkerHarness();
    await harness.deliver({ source: 'no driver here' });
    expect(harness.reports).toEqual([]);
  });
});

describe('worker bootstrap origin guard', () => {
  it('refuses cross-origin requests', () => {
    const harness = createWorkerHarness();
    expect(() => harness.scope.fetch('https://example.com/data')).toThrow(/may only reach/);
    expect(() =>
      harness.scope.XMLHttpRequest.prototype.open.call({}, 'GET', 'https://example.com/data')
    ).toThrow(/may only reach/);
    expect(() => harness.scope.WebSocket('https://example.com/socket')).toThrow(/may only reach/);
    expect(() => harness.scope.EventSource('https://example.com/stream')).toThrow(/may only reach/);
    expect(() => harness.scope.WebTransport('https://example.com/transport')).toThrow(
      /may only reach/
    );
    expect(() => harness.scope.importScripts('https://example.com/engine.js')).toThrow(
      /may only reach/
    );
    // Nothing reached the network: a refused target leaves no trace.
    expect(harness.fetches).toEqual([]);
    expect(harness.socketUrls).toEqual([]);
    expect(harness.eventSourceUrls).toEqual([]);
    expect(harness.transportUrls).toEqual([]);
    expect(harness.imports).toEqual([]);
  });

  it('allows same-origin requests', async () => {
    const harness = createWorkerHarness();
    await harness.scope.fetch('/api/health');
    harness.scope.XMLHttpRequest.prototype.open.call({}, 'GET', '/api/health');
    harness.scope.WebSocket(`${WORKER_WS_ORIGIN}/socket`);
    harness.scope.EventSource('/events');
    harness.scope.importScripts(SKULPT_ENGINE_URL);
    expect(harness.fetches).toEqual([{ url: '/api/health', init: { redirect: 'error' } }]);
    expect(harness.xhrOpens).toEqual(['/api/health']);
    expect(harness.socketUrls).toEqual([`${WORKER_WS_ORIGIN}/socket`]);
    expect(harness.eventSourceUrls).toEqual(['/events']);
    expect(harness.imports).toEqual([SKULPT_ENGINE_URL]);
  });

  it('allows a WebSocket to the host the app is served from', () => {
    const harness = createWorkerHarness();
    expect(() => harness.scope.WebSocket(`${WORKER_WS_ORIGIN}/socket`)).not.toThrow();
    expect(harness.socketUrls).toEqual([`${WORKER_WS_ORIGIN}/socket`]);
  });

  it('refuses a WebSocket to another host', () => {
    const harness = createWorkerHarness();
    expect(() => harness.scope.WebSocket('ws://example.com/socket')).toThrow(/may only reach/);
    expect(harness.socketUrls).toEqual([]);
  });

  it('refuses a secure WebSocket from an insecure page', () => {
    const harness = createWorkerHarness();
    expect(() => harness.scope.WebSocket('wss://localhost:5173/socket')).toThrow(/may only reach/);
  });

  it('refuses a WebTransport to another host', () => {
    const harness = createWorkerHarness({ secure: true });
    expect(() => harness.scope.WebTransport('https://example.com/transport')).toThrow(
      /may only reach/
    );
    expect(harness.transportUrls).toEqual([]);
  });

  it('allows a WebTransport to the host the app is served from', () => {
    const harness = createWorkerHarness({ secure: true });
    const transport = `${workerOrigin(true)}/transport`;
    expect(() => harness.scope.WebTransport(transport)).not.toThrow();
    expect(harness.transportUrls).toEqual([transport]);
  });

  it('keeps the native socket constructors out of reach', () => {
    const harness = createWorkerHarness();
    expect(harness.scope.WebSocket.prototype.constructor).toBe(harness.scope.WebSocket);
    expect(harness.scope.EventSource.prototype.constructor).toBe(harness.scope.EventSource);
    expect(harness.scope.WebTransport.prototype.constructor).toBe(harness.scope.WebTransport);
    const socket = harness.scope.WebSocket.prototype.constructor as typeof harness.scope.WebSocket;
    expect(() => socket('ws://example.com/socket')).toThrow(/may only reach/);
  });
});

describe('worker bootstrap request targets', () => {
  it('refuses a cross-origin URL object', () => {
    const harness = createWorkerHarness();
    const target = new URL('https://example.com/data');
    expect(() => harness.scope.fetch(target)).toThrow(/may only reach/);
    expect(harness.fetches).toEqual([]);
  });

  it('refuses a cross-origin request object', () => {
    const harness = createWorkerHarness();
    const target = { url: 'https://example.com/data' };
    expect(() => harness.scope.fetch(target)).toThrow(/may only reach/);
    expect(harness.fetches).toEqual([]);
  });

  it('allows a same-origin URL object', async () => {
    const harness = createWorkerHarness();
    const target = `${WORKER_ORIGIN}/api/health`;
    await harness.scope.fetch(new URL(target));
    expect(harness.fetches).toEqual([{ url: target, init: { redirect: 'error' } }]);
  });

  it('refuses a target that carries no URL at all', () => {
    const harness = createWorkerHarness();
    expect(() => harness.scope.fetch({})).toThrow(/may only reach/);
    expect(harness.fetches).toEqual([]);
  });
});

describe('worker bootstrap redirect policy', () => {
  it('follows no redirect', async () => {
    const harness = createWorkerHarness();
    await harness.scope.fetch('/api/health');
    // A redirect leaves the origin and its target cannot be checked before the
    // request is on the wire, so the guarded fetch refuses to follow one.
    expect(harness.fetches).toEqual([{ url: '/api/health', init: { redirect: 'error' } }]);
  });
});

describe('worker bootstrap script loads', () => {
  it('loads every script importScripts is given', () => {
    const harness = createWorkerHarness();
    harness.scope.importScripts(SKULPT_ENGINE_URL, SKULPT_STDLIB_URL);
    expect(harness.imports).toEqual([SKULPT_ENGINE_URL, SKULPT_STDLIB_URL]);
  });

  it('refuses a foreign script among same-origin ones', () => {
    const harness = createWorkerHarness();
    expect(() =>
      harness.scope.importScripts(SKULPT_ENGINE_URL, 'https://example.com/engine.js')
    ).toThrow(/may only reach/);
    // The refused batch loads nothing: the check runs before the load.
    expect(harness.imports).toEqual([]);
  });
});

describe('worker bootstrap guard ownership', () => {
  it('takes the native APIs off the prototype chain', () => {
    const harness = createWorkerHarness();
    const prototype = harness.prototype;
    for (const name of [
      'fetch',
      'XMLHttpRequest',
      'WebSocket',
      'EventSource',
      'WebTransport',
      'importScripts',
    ]) {
      expect(prototype[name]).toBeUndefined();
      expect(typeof (harness.scope as SnippetScope)[name]).toBe('function');
    }
  });

  it('keeps the natives out of reach through the prototype chain', () => {
    const harness = createWorkerHarness();
    // The path a snippet takes to bypass the guard: the prototype of the
    // worker global carries no native any more.
    expect(harness.evaluate('typeof Object.getPrototypeOf(self).fetch')).toBe('undefined');
    expect(harness.evaluate('typeof Object.getPrototypeOf(self).importScripts')).toBe('undefined');
    expect(harness.evaluate('typeof Object.getPrototypeOf(self).WebSocket')).toBe('undefined');
    expect(harness.evaluate('typeof Object.getPrototypeOf(self).Worker')).toBe('undefined');
  });

  it('offers no nested worker', () => {
    const harness = createWorkerHarness();
    expect((harness.scope as SnippetScope).Worker).toBeUndefined();
  });

  it('keeps a guarded API when a snippet tries to take it', () => {
    const harness = createWorkerHarness();
    const scope = harness.scope as SnippetScope;
    const descriptor = Object.getOwnPropertyDescriptor(scope, 'fetch');
    expect(descriptor?.writable).toBe(false);
    expect(descriptor?.configurable).toBe(false);
    // A snippet that deletes or replaces the guard gets nothing: the property
    // is locked, and the native behind it is gone from the prototype chain.
    expect(() => {
      delete scope.fetch;
    }).toThrow(TypeError);
    expect(() => {
      scope.fetch = () => 'replaced';
    }).toThrow(TypeError);
    expect(() => (scope.fetch as (input: string) => void)('https://example.com/data')).toThrow(
      /may only reach/
    );
  });

  it('locks the URL constructor the origin check reads', () => {
    const harness = createWorkerHarness();
    const scope = harness.scope as SnippetScope;
    const descriptor = Object.getOwnPropertyDescriptor(scope, 'URL');
    expect(descriptor?.writable).toBe(false);
    expect(descriptor?.configurable).toBe(false);
    // A constructor that reports every origin as its own must not be able to
    // take the place of the one the check uses.
    expect(() => {
      scope.URL = class {
        static parse(): unknown {
          return { protocol: 'https:', origin: 'https://example.com', host: 'example.com' };
        }
      };
    }).toThrow(TypeError);
    expect(() => (scope.fetch as (input: string) => void)('https://example.com/data')).toThrow(
      /may only reach/
    );
  });
});

describe('worker bootstrap socket constants', () => {
  it('keeps the state constants on the replacement constructors', () => {
    const harness = createWorkerHarness();
    expect(harness.scope.WebSocket.CONNECTING).toBe(0);
    expect(harness.scope.WebSocket.OPEN).toBe(1);
    expect(harness.scope.WebSocket.CLOSING).toBe(2);
    expect(harness.scope.WebSocket.CLOSED).toBe(3);
    expect(harness.scope.EventSource.CONNECTING).toBe(0);
    expect(harness.scope.EventSource.OPEN).toBe(1);
    expect(harness.scope.EventSource.CLOSED).toBe(2);
  });
});
