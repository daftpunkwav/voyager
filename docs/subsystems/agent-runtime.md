# Agent runtime machinery

English | [中文](agent-runtime.zh.md)

The resident machinery under `agent/src/agent/runtime/`, plus hooks and plugins.

## Trajectory

`trajectory.py` — `TrajectoryStore` (`data/runtime/agent/trajectory.db`) is a rebuildable query projection over the event log. `catch_up()` (single writer, idempotent `INSERT OR IGNORE` by `seq`) folds `agent.step` and run-lifecycle events into `steps` and `runs` tables, with a cursor in `meta`. The `raw_rounds` table (`PRIMARY KEY (run_id, round)`) stores full request/response JSON per round plus `wire_request` (the exact outbound wire body) and `seq_round` (a per-session continuous display round number, backfilled in a single transaction ordered by `ts`; reads order by it). Written via `master.sessions.set_raw_fn` for conversational instances only. Raw rows purge after `RAW_LOG_RETENTION_DAYS = 7`. Each `agent.step` event nudges `catch_up()` inline (`runtime/wire.py`). The gateway's `GET /api/chat/trajectory` and `GET /api/chat/rawllm` read this store.

## Session index

`session_index.py` — `SessionIndex` (`data/runtime/agent/session_index.db`): SQLite FTS5 search projection over `user.message`/`agent.message` with CJK token splitting.

## Durable queue and scheduler

`queue_store.py` — `QueueStore` (`data/runtime/agent/queue.db`): durable queue with cron support, at-least-once delivery, and crash recovery (`recover()` at boot). `scheduler.py` — `Scheduler`: the concurrency cap for subagent runs, timers, and the durable-job poll loop (`app.start_queue_loop`). `wake_budget.py` gates how often queued work may wake the agent.

## Metering and quota

`meter.py` / `meter_store.py` / `pricing.py` — `Meter` over `MeterStore` (`meter.db`), 90-day purge; every LLM call and tool call records usage. `runtime/llm_quota.py` — `metered_llm(client, meter, quota_fn)` wraps every real LLM client, hot-reading the daily token budget `agent.resource.daily_tokens`. `agent.pricing.overrides` feeds cost conversion.

## Deadlines, retries, breakers

`deadline.py` — `Deadline.from_settings` applies wall-clock caps `agent.execution.tool_deadline_s` / `round_deadline_s`. `recovery.py` — `with_retry` and `CircuitBreaker` (per tool and per event pattern).

## Checkpoints and resume

`state.py` — `RunState`, `Step`, `ResumeSnapshot`, and `CheckpointStore` (`data/runtime/agent/checkpoints/`) with atomic saves and startup sweeps; `build.py` purges temp files and prepares resumable checkpoints at boot. `Spawner.resume_from_checkpoint` replays task-mode REACT runs; a pause persists `pending_messages` mid-turn.

## Tracing and observability

`trace.py` — trace `ContextVar` plus a bounded span buffer (`start_span`). `exporters.py` — `TraceDispatcher` selects OTLP and/or Langfuse exporters per `agent.observability.exporter`. `evaluation.py` — `TaskEvaluator` scores turns heuristically or with a judge (`agent.evaluation.*`). `jobs_view.py` — `JobsView`, a read-only `task.*` projection backing the jobs API. `current.py` — the `current_instance` context variable.

## Write journal

`build.py` wires `WriteJournal` (`data/runtime/agent/write_journal/`): content-addressed backups of file writes supporting undo.

## Hooks

`hooks/triggers.py` — `HookRegistry` with fixed points: `on_event`, `pre_tool` (returning `False` blocks), `post_tool`, `on_subagent_start`, `on_subagent_end`, `on_user_message`. `hooks/loader.py` — `HookLoader.load_dir` loads `workspace/hooks`; `hooks/reload.py` — `UserHookReloader` hot-loads and hot-unloads hook files and syncs declarative `on_event` patterns into the `EventLoop`.

## Plugins

`agent/src/agent/plugins/manager.py` — `PluginManager` discovers `<plugins_root>/<name>/plugin.json` manifests. Loading is restricted to the persisted approval lists (`agent.plugins.approved`, `agent.plugins.approvals`); the manager applies a plugin's skills, hooks, and MCP entries declaratively and never imports or executes plugin code. `agent/src/agent/plugins/install.py` — zip/directory install behind manifest, path-jail, zip-slip, symlink, and size validation; installed plugins are never pre-approved; uninstall removes only unapproved plugins.
