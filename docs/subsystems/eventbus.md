# Event bus

English | [中文](eventbus.zh.md)

The event bus is the integration backbone: domains never import each other, they publish and subscribe. `platform_eventbus` provides the append-only log, the in-process fan-out, and the cursor store.

Source: `packages/platform/eventbus/src/platform_eventbus/`

## Event vocabularies

`platform_contracts/events.py` declares two families, extended by the agent:

- **`DomainEvent`** — cross-domain facts on the bus. Fixed names include: `user.message`, `user.online`, `user.activity`, `task.enqueued`/`task.progress`/`task.completed`/`task.failed`, `agent.message`, `agent.ask`, `agent.step`, `agent.delta`, `agent.observe`, `agent.policy.notify`, `agent.navigate`, `skill.proposed`, `session.deleted`, `settings.changed`, `service.health.changed`. Domains add their own (`note.created`…`note.purged`, `notes.ui.changed`, `doc.created`, `doc.edited`, `source.added`/`source.removed`/`source.ready`, `graph.engine.fallback`).
- **`RuntimeEvent`** — agent run lifecycle (`RunStarted`, `LLMStarted`, `LLMStreaming`, `LLMCompleted`, `ToolStarted`, `ToolCompleted`, `ToolFailed`, `AgentPaused`, `AgentResumed`, `AgentCompleted`, `AgentCancelled`, `RunFailed`, `RunCancelled`); `agent/src/agent/runtime/events.py` extends it with `ToolProgress` and `ThinkingStarted`/`ThinkingDelta`/`ThinkingCompleted`.

Every event carries `seq` (log position), `type`, `ts`, `trace_id`, and payload.

## EventLog

`EventLog` appends every event to a SQLite `events` table keyed by autoincrement `seq` and serves paged reads (`before_seq`/`after_seq`) and catch-up scans. This log — not memory — is the source of truth: chat history, trajectory rebuilds, and SSE replay all read from it. `Retention` sweeps old rows by type and age; the host configures retention for `agent.delta` only (24 h), so all other event types accumulate until purged manually.

## EventBus

`EventBus` delivers each committed event to in-process async subscribers by glob-style pattern (`*` supported). A subscriber that falls too far behind is flagged `lagged` instead of being dropped silently; it recovers by replaying from the log at its stored position. The gateway's SSE endpoint (`GET /api/chat/stream`) is a remote consumer: it streams live fan-out and replays missed rows from the log when the client reconnects with `after_seq`.

## CursorStore

`CursorStore` persists per-subscriber positions so an `EventLoop` (the agent's dispatcher) resumes where it stopped instead of reprocessing the log on boot.

## Producers and consumers

| Producer | Event | Main consumers |
|---|---|---|
| gateway `POST /api/chat/messages` | `user.message` | agent `EventLoop` → `Master.handle_user_message`; chat history API |
| gateway `POST /api/activity` | `user.activity` | activity feed API |
| agent ReAct round loop | `agent.step`, `agent.delta`, `agent.message` | trajectory projection, SSE → frontend trace and bubbles |
| agent policy | `agent.policy.notify` | no live consumer: the frontend drops them (the step trail and the activity page carry the calls) |
| domain workers (notes/sources/graph/code_exec) | `task.progress`/`task.completed`/`task.failed` | SSE → frontend job progress |
| `SettingsStore` | `settings.changed` | settings-dependent hot readers |
| domain wirings | lifecycle facts (`note.created`, `source.ready`, …) | frontend feeds; hooks (`on_event`) |
