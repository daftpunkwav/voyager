/**
 * @file codeRunnerWorker
 * @description Unit coverage for the worker bootstrap the app ships
 * (public/code-runner-worker.js).
 *
 * The bootstrap installs the engine driver the page sends and holds the runner
 * to the page origin, so the tests run that file in a simulated worker scope:
 * a broken message handler or a missing origin guard has to fail them.
 */

import { describe, expect, it } from 'vitest';
import {
  createWorkerHarness,
  SKULPT_ENGINE_URL,
  WORKER_WS_ORIGIN,
  workerOrigin,
} from './helpers/workerHarness';

/** Minimal driver: the bootstrap only has to install and run what the page sends. */
const DRIVER_STUB = `self.onmessage = function (event) {
  self.postMessage({ ok: true, driver: 'installed' });
};`;

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
    expect(harness.fetches).toEqual(['/api/health']);
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
