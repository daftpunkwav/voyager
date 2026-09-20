# gateway (src) — HTTP transport

This directory implements the HTTP transport layer: mounting domain routers, chat SSE, session bootstrap, uploads, the activity feed, health probing, and rate limiting. The package-level contract lives in [packages/gateway/README.md](../../../README.md); the subsystem walkthrough lives in [docs/subsystems/gateway.md](../../../../docs/subsystems/gateway.md). This file only maps what each file here contains.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `activity.py` | `POST /api/activity` user-activity reporting (publishes `user.activity` events, no business interpretation) and `GET /api/activity/feed` rebuilt from the event log. |
| `chat.py` | Chat channel: `POST /api/chat/messages` publishes `user.message`; `GET` history pages from the event log, while trajectory reads the injected projection when present and falls back to the event log; `GET /api/chat/stream` delivers SSE with `after_seq` resume. |
| `health.py` | `HealthProbe`: passively probes mounted packages, keeps only the health snapshot, and publishes `service.health.changed` on transitions. |
| `mounts.py` | `MountSpec` and `mount_services`: attaches each service's registry-generated router under `/api/<domain>/`, plus optional per-domain `extra_router`. |
| `ratelimit.py` | `RateLimiter`: in-memory per-actor sliding window per minute plus a concurrent-SSE cap; over-limit raises `GATEWAY.RATE_LIMITED` (429). |
| `rest.py` | App assembly: `create_app` (mount list and lifespan injected by the deployment entry point) / `app_factory`; resolves the HTTP actor and installs the global `ServiceError` envelope. |
| `session.py` | `GET /api/session/bootstrap`: loopback-only issuance of an HttpOnly cookie so the browser carries credentials. |
| `settings.py` | `SettingDef`s for `gateway.*` keys (rate limit per minute, SSE connection cap, chat history page size); values are read and injected by the composition root. |
| `uploads.py` | `POST /api/uploads`: lands browser uploads under `workspace/imports/` and returns the server-side path; business validation stays in domain capabilities. |
| `workspace.py` | Read-only workspace browsing (`/api/workspace/list`, `/read`) and a machine-wide directory picker (`/pick`); root switching is the host-owned `/api/workspace/switch`. |

## Entry points

- Standalone: `uvicorn gateway.rest:app_factory --factory --port 8000` — empty mounts, only session/chat/activity/health (per `rest.py` docstring).
- Aggregated: `create_app(mounts=...)` is called by `packages/host/` with the `MountSpec` list, lifespan, and limiter configuration injected.
