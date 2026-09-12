# gateway

## Purpose

HTTP transport: capability mounting, chat SSE, uploads, activity feed, health, rate limiting, security headers.

## Configuration

gateway.* settings: rate limit per minute, SSE connection cap.

## Extension Points

New transport route = one router module under this package; business logic stays in domains.

## Model Experience

Model-agnostic transport; agents reach capabilities through the bridge, humans through REST.

## Known Limitations

Single instance only (in-memory rate limiter/SSE state).

## Deferred Work

WebSocket transport.
