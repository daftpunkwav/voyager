/**
 * @file stream.ts
 * @description SSE event stream: singleton EventSource with pattern-based subscription;
 * reconnects carry the last seen seq so no events are lost.
 *
 * Responsibilities:
 * - Hold the singleton EventSource connection (credential auth) and parse
 *   frames into StreamEvent objects
 * - Reconnect manually with after_seq resume and exponential backoff
 * - Dispatch events to subscribers by fnmatch-style patterns; open on the
 *   first subscriber, close on the last unsubscribe
 *
 * This module must not depend on UI-layer components.
 */

export interface StreamEvent {
  seq: number;
  type: string;
  actor?: Record<string, unknown>;
  payload: Record<string, unknown>;
  trace_id?: string;
  ts?: number;
}

type Handler = (event: StreamEvent) => void;

let source: EventSource | null = null;
let lastSeq = 0;
let started = false;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retryDelay = 1000;
const RETRY_DELAY_MAX = 30_000;
const handlers = new Set<{ patterns: string[]; fn: Handler }>();

function connect(): void {
  // Close the old connection before creating a new one: overwriting the reference
  // during a reconnect race would orphan the old EventSource (still receiving,
  // never closed)
  if (source) {
    source.close();
    source = null;
  }
  // after_seq = lastSeq: after a reconnect, events missed during the outage are replayed from the log
  const url = lastSeq > 0 ? `/api/chat/stream?after_seq=${lastSeq}` : '/api/chat/stream';
  const es = new EventSource(url, { withCredentials: true });
  source = es;
  es.onopen = () => {
    retryDelay = 1000; // Connection restored; reset the backoff
  };
  es.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as StreamEvent;
      const seq = typeof event.seq === 'number' ? event.seq : Number.parseInt(msg.lastEventId, 10);
      if (Number.isFinite(seq) && seq > lastSeq) {
        lastSeq = seq;
      }
      for (const h of handlers) {
        if (h.patterns.some((p) => matchPattern(p, event.type))) h.fn(event);
      }
    } catch {
      // Ignore non-JSON frames (heartbeat comment frames never reach onmessage)
    }
  };
  es.onerror = () => {
    // The browser's native EventSource would auto-reconnect without after_seq;
    // rebuild manually to resume from the last seq
    es.close();
    source = null;
    if (handlers.size === 0) {
      started = false;
      return;
    }
    // Re-check subscribers when the timer fires: all of them may have unsubscribed
    // while a retry was scheduled — never raise a zero-subscriber connection
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = setTimeout(() => {
      retryTimer = null;
      if (handlers.size > 0) {
        connect();
      } else {
        started = false;
      }
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, RETRY_DELAY_MAX); // Exponential backoff; reset on connect
  };
}

function matchPattern(pattern: string, type: string): boolean {
  // Glob semantics: '*' matches any (possibly empty) substring, in any position.
  const re = new RegExp('^' + pattern.split('*').map(escapeRe).join('.*') + '$');
  return re.test(type);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Subscribe to events (supports *.type wildcards); returns an unsubscribe function.
 *  The first subscriber opens the connection; the last unsubscribe closes it. */
export function subscribe(patterns: string[], fn: Handler): () => void {
  const entry = { patterns, fn };
  handlers.add(entry);
  if (!started) {
    started = true;
    connect();
  }
  return () => {
    handlers.delete(entry);
    if (handlers.size === 0) {
      // Last subscriber left: cancel any pending reconnect too, otherwise the
      // timer would raise a zero-subscriber connection
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      if (source) {
        source.close();
        source = null;
      }
      started = false;
    }
  };
}
