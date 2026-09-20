# Agent subagents and orchestration

English | [中文](agent-subagents.zh.md)

How the engine spawns, bounds, and coordinates subagent runs.

Source: `agent/src/agent/subagent/` plus `master/` orchestration modules.

## Instances and task books

`instance.py` — `SubagentInstance` is one run's state machine: `task: TaskBook`, toolbelt, LLMs, `state: RunState`, history, `UsageTracker`, persona, `parent_run_id` (cancel cascade), deadline, budget, `prefix_watch`. `TaskBook` (frozen dataclass) declares a run: `goal`, `constraints`, `done_when`, `mode`, `allowed_tools` (None = no trim, `()` = no tools), `readonly`, `limits`, `conversational`, `session`, `depends_on`. Status machine (`SubStatus`): `created → running → waiting_input → completed/failed/cancelled`.

## Spawning

`spawn.py` — `Spawner`:

- `spawn(task, persona, name, ...)` builds a narrowed toolbelt: `trimmed(allowed_tools)`, plus `trimmed_read_only()` when `readonly`.
- `start(inst, user_text)` runs the turn under the `Scheduler` concurrency cap (`agent.subagents.max_concurrent`) and persists a turn-boundary checkpoint in `finally`.
- `resume_from_checkpoint(run_id)` — task-mode REACT only.
- `cancel(id_or_name)` cascades to running and pending descendants via `parent_run_id`.
- Terminal instances evict beyond `TERMINAL_INSTANCE_CAP = 32` (oldest first).

`registry.py` — `SubagentRegistry`/`SubagentDef`: user-defined subagents persisted as JSON under `data/runtime/subagents/*.json` (name must match `^[a-z][a-z0-9_]*$`; fields cover mode, persona, allowed tools, limits, network mode, readonly, enabled).

`surface.py` — `intersect_surface` enforces assignment-time narrowing: a dispatch can never grant a wider tool surface than the dispatcher holds.

`triggered_spawn.py` — event-pattern-triggered spawns with cooldown `agent.triggers.cooldown_s`.

## Modes

`modes/registry.py` dispatches `run_mode()` over seven modes, one file each: `react`, `plan_execute`, `cot`, `tot`, `got`, `reflexion`, `direct`. The orchestrator persona is forced to ReAct (`master/dispatch.py`). `wait` on a subagent is the `subagent` capability's `wait` action: polls at 0.5 s, default timeout 120 s, cap 600 s.

## Orchestration (`master/`)

- **Task graph** (`task_graph.py`) — parent/child tree of dispatches with a depth cap (`agent.subagents.max_depth`, default 3); unmet `depends_on` holds a dispatch as `DeferredDispatch`; `finish_task` joins the graph. Not a general DAG engine.
- **Dispatch** (`dispatch.py`) — persona resolution (built-in → user registry fallback), surface intersection, network narrowing (`narrow_network`), background run, completion notice synthesis (`synthesize.py`), `on_subagent_start`/`on_subagent_end` hooks.
- **Blackboard** (`blackboard.py`) — task-scoped shared notes; instances never talk directly.
- **Digests** (`digest.py`) — `DigestStore` keeps per-subagent status cards; the orchestrator sees digests, never raw context.
- **Arbiter** (`arbiter.py`) — merges/queues/defers new user input while a turn is running (`agent.arbiter.mode`).
- **Goals** (`goal.py`, `goal_driver.py`) — one durable goal per session in the session-store meta; the driver schedules reservation-gated continuation rounds through the durable queue; boot never auto-revives a paused goal.
- **Proactive** (`proactive.py`, `outreach_budget.py`) — greeting on `user.online` and one follow-up chain from the durable queue, capped by `agent.outreach.*` budgets.
- **Job notifier** (`job_notify.py`) — scheduler completions produce a quiet notice or a budget-gated wake turn.
