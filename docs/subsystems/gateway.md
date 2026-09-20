# Gateway

English | [中文](gateway.zh.md)

The `gateway` domain is the single HTTP carrier. It imports no domain; domains appear as mounted routers. In the composed process, host builds one gateway app serving every domain under `/api/<domain>` on port 8000; standalone, `uvicorn gateway.rest:app_factory --factory --port 8000` runs with its own default DB (`packages/gateway/data/events.db`).

Source: `packages/gateway/src/gateway/`

## Application

`rest.py` — `create_app(mounts, db_path, bus, lifespan, issuer, auth, quota, audit, rate_limit_per_minute=600, sse_max_connections=8, ...)`:

- Security-header middleware: CSP mirroring the frontend's `index.html` meta CSP (`frame-ancestors 'none'`, `script-src 'self' 'unsafe-eval' blob:`, `worker-src 'self' blob:`), `X-Content-Type-Options: nosniff`.
- Actor middleware: `platform_actor.resolve_http_actor` resolves Bearer/cookie callers; unauthenticated loopback requests act as `LOCAL_USER`; unauthenticated non-loopback requests get 401.
- `ServiceError` handlers render the `ErrorEnvelope` (`{error: {code, message, hint, trace_id}}`).

## Mounted routers

| Router | Endpoints | Notes |
|---|---|---|
| `mounts.py` | `GET /api/<domain>/capabilities`, `POST /api/<domain>/capabilities/{name}` | one `MountSpec` per domain registry (`build_router`) |
| `chat.py` | `POST /api/chat/messages`, `GET /api/chat/messages`, `GET /api/chat/trajectory`, `GET /api/chat/rawllm`, `GET /api/chat/stream` | history pages take `before_seq`/`after_seq`/`session`; SSE carries `after_seq` resume, backlog replay (`once=true`), keep-alive comments, and a `_STREAM_TYPES` filter |
| `session.py` | `GET /api/session/bootstrap` | loopback-only HttpOnly session cookie, 30-day TTL |
| `activity.py` | `POST /api/activity`, `GET /api/activity/feed` | kinds `page_view`/`pointer`/`selection`/`manual` → publishes `user.activity` |
| `uploads.py` | `POST /api/uploads` | multipart, 1 GiB cap, lands under `workspace/imports/` |
| `workspace.py` | `GET /api/workspace/list`, `GET /api/workspace/read`, `GET /api/workspace/pick` | `read` caps previews at 256 KiB / 400 lines; `pick` browses any directory read-only |
| `health.py` | `GET /health` | aggregates `HealthProbe`s |

Host adds extra routers on top (`build_upload_router`, `build_workspace_router`, `build_switch_router`, jobs routers) and mounts the agent registry as `MountSpec(domain="agent", ...)`.

## Rate limiting and SSE capacity

`ratelimit.py` — in-memory `RateLimiter` keyed per caller, ceiling `gateway.rate_limit.per_minute` (single-instance only). SSE capacity is capped by `gateway.sse.max_connections`.

## Agent-facing surface parity

The gateway is the human side of the parity contract pinned by `agent/src/agent/parity.py`: every capability reachable over REST is callable by the agent tool of the same `<domain>__<capability>` name, and the host parity test keeps the two in check.
