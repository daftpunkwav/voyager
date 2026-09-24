# Agent subagents and orchestration

English | [中文](agent-subagents.zh.md)

How the engine spawns, bounds, and coordinates subagent runs.

Source: `agent/src/agent/subagent/` plus `master/` orchestration modules.

## Instances and task books

`instance.py` — `SubagentInstance` is one run's state machine: `task: TaskBook`, toolbelt, LLMs, `state: RunState`, history, `UsageTracker`, persona, `parent_run_id` (cancel cascade), deadline, budget, `prefix_watch`. `TaskBook` (frozen dataclass) declares a run: `goal`, `constraints`, `done_when`, `mode`, `allowed_tools` (None = no trim, `()` = no tools), `readonly`, `limits`, `conversational`, `session`, `depends_on`, `board_task_id` (team task-board row back-link). Status machine (`runtime/state.py:RunStatus`): `pending → running → waiting_input/paused → completed/failed/cancelled`.

## The resident team (group chat)

One chat session is a group chat among the resident team: the five built-in personas (`personas/TEAM_KEYS` — orchestrator/Lucien, recon/Iris, explainer/Elio, organizer/Miyai, graph_guide/Atlas). Members share the session transcript; every agent reply carries a `speaker` (persona key, persisted on the history entry and on the `agent.message` payload; absent = the host, which is also how pre-team messages read).

- **Member turns** — `subagent/turn.py:run_turn(inst, text, member=persona_key)` runs the turn under that persona (own system layers via `build_system`, tool surface `trimmed(tool_allow)`, own `default_mode` — explainer runs cot in-session) over the shared transcript; the request renders teammates' historical replies with a `【name】` prefix and merges consecutive assistant entries (several providers reject adjacent assistant turns). The member label rides `inst._member_label` so step/delta events attribute to "Elio", not the session's generic "chat".
- **Floor routing** — `master/master.py:_parse_mention` routes a leading `@Name` (display names and aliases) straight to that member; `subagent(action=handoff, persona, message)` queues a member turn through the session inbox (drained after the current turn ends, same per-session lock — one speaker at a time).
- **Task board** — `master/task_board.py:TaskBoard` is the publish/claim/confirm state machine (`open → claimed → assigned → running → done/failed`, in-memory, lifetime matching dispatched instances). The `taskboard` capability (and same-name tool) exposes `publish/claim/confirm/list` to humans and agents alike: Lucien publishes after scoping with the user, a member claims with a negotiation note, the publisher confirms and the capability dispatches the run in the background (`TaskBook.board_task_id` links the row). A claim wakes the publisher (`Master.notify_task_claim`) to confirm or answer the note.
- **Deliveries** — a board run's completion goes through `Master.announce_delivery`: the board row is stamped, a structured `agent.delivery` event (full content, status, elapsed, `run_id`) lands on the timeline as the frontend's delivery card, and the host relays a synthesized summary via a wake turn (`handle_notice`, gated by `WakeBudget` — over budget it degrades to a quiet receipt; claims always wake).

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

`modes/registry.py` dispatches `run_mode()` over seven modes, one file each: `react`, `plan_execute`, `cot`, `tot`, `got`, `reflexion`, `direct`. Dispatches ride the persona's `default_mode`; resident-host chat turns stay ReAct, while member turns (@-mention / handoff / board runs) use the member persona's `default_mode` (explainer runs cot). `wait` on a subagent is the `subagent` capability's `wait` action: polls at 0.5 s, default timeout 120 s, cap 600 s.

## Orchestration (`master/`)

- **Task graph** (`task_graph.py`) — parent/child tree of dispatches with a depth cap (`agent.subagents.max_depth`, default 3); unmet `depends_on` holds a dispatch as `DeferredDispatch`; `finish_task` joins the graph. Not a general DAG engine.
- **Dispatch** (`dispatch.py`) — persona resolution (built-in → user registry fallback), surface intersection, network narrowing (`narrow_network`), background run, completion notice synthesis (`synthesize.py`), `on_subagent_start`/`on_subagent_end` hooks.
- **Blackboard** (`blackboard.py`) — task-scoped shared notes; instances never talk directly.
- **Task board** (`task_board.py`) — team publish/claim/confirm rows (see the resident-team section); `Master.announce_delivery` stamps the row, emits `agent.delivery`, and relays the report.
- **Digests** (`digest.py`) — `DigestStore` keeps per-subagent status cards; the orchestrator sees digests, never raw context.
- **Arbiter** (`arbiter.py`) — merges/queues/defers new user input while a turn is running (`agent.arbiter.mode`).
- **Goals** (`goal.py`, `goal_driver.py`) — one durable goal per session in the session-store meta; the driver schedules reservation-gated continuation rounds through the durable queue; boot never auto-revives a paused goal.
- **Proactive** (`proactive.py`, `outreach_budget.py`) — greeting on `user.online` and one follow-up chain from the durable queue, capped by `agent.outreach.*` budgets.
- **Job notifier** (`job_notify.py`) — scheduler completions produce a quiet notice or a budget-gated wake turn.
