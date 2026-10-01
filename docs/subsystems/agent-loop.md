# Agent loop

English | [中文](agent-loop.zh.md)

The agent engine is event-driven: it owns no request handler. A bus event starts work, asyncio tasks drive turns, and durable stores record everything. Source root: `agent/src/agent/` (package `agent`).

## Assembly

`build.py` — `build_agent(*, data_dir="data/runtime", workspace_dir=None, llm=None, ...) -> AgentApp` is the single composition root. It constructs the event log and bus, settings, memory, policy engine, meter, toolbelt, MCP pool, plugin manager, scheduler, queue, checkpoints, trajectory, session index, master, goal manager/driver, and the event loop, then binds them together. The assembled parts live on `AgentApp` (`app.py`): `bus`, `log`, `settings`, `memory`, `master`, `loop`, `skills`, `hooks`, `pages`, `asker`, `spawner`, `registry`, `mcp`, `meter`, `plugins`, `user_hooks`, `session_store`, `trajectory`, `queue_store`, `scheduler`, `checkpoints`, `write_journal`, `session_index`, `dispatcher`. `app.close()` releases them; `drain()` waits for background turns.

When no LLM is injected (standalone run without configuration), `build_agent` degrades to `FakeLLM` with a warning.

Process entry: `main.py` — `python -m agent.main` calls `build_agent()` then `await app.loop.run()`. `repl.py` provides a standalone terminal client.

## Event wiring

`runtime/wire.py` — `bind_event_loop(...)` maps bus patterns to handlers: `user.message` → `Master.handle_user_message`, `agent.step` → `trajectory.catch_up`, `user.online` → proactive greeting, plus subagent trigger patterns. `runtime/loop.py` — `EventLoop` drains pending log rows via the stored cursor, then subscribes and dispatches with a per-pattern `CircuitBreaker`; the `"*"` pattern is refused.

## Turn driving

`orchestrator/master.py` — `Master.handle_user_message(text, trace_id, session_id)`:

1. Fire the `on_user_message` hook; append to working memory; optionally run `Distiller.maybe_distill()`.
2. Direct-chat mode (`agent.direct_chat`): answer with one completion.
3. Otherwise resolve or create the chat session (`SessionManager`), and if the instance is already RUNNING, apply the `Arbiter` (merge / queue / enqueue-notify per `agent.arbiter.mode`; auto and guide modes use a short LLM judge and fall back to queue on failure).
4. `_start_turn` backgrounds `Master._turn` in an asyncio task under the per-session lock (`sessions.lock_for`), drains the session inbox afterwards, then `goal_driver.maybe_schedule(session)`.

A leading `@Name` (`_parse_mention`) routes the message to that resident teammate as a member turn (`run_turn(member=...)` — the persona's own system layers, tool surface, and default mode over the shared transcript); while a turn is running the mention parks in the same inbox. Inbox entries carry the speaker (`_Queued.member`), so drained member turns hand the floor to the named teammate. Team completions arrive as `Master.announce_delivery` → a structured `agent.delivery` event plus a wake turn that relays the report (gated by `WakeBudget`; over budget it degrades to a quiet receipt). Task-board claims always wake the publisher — adjudicating a claim is the flow, not a completion echo.

`Master._turn` re-applies limits from settings, sets the instance deadline, and calls `Spawner.start(inst, text)` → `SubagentInstance.run_turn` (`engine/turn.py`) → `run_mode(Mode.REACT, ...)` → `modes/react.py:run_react`.

## The ReAct round

Each round in `run_react`:

1. `governor.enforce` — deterministic prune, then LLM compaction if still over threshold.
2. `complete_streaming(llm, messages, specs, ...)` — one model request; usage and raw request/response are recorded (`on_step`, `on_raw`).
3. If the reply carries final text, return it. The final text is the turn's only delivered message — intermediate round narration stays on the step trail (the chat UI shows it inside the execution trace). A no-tool non-chitchat answer may trigger one `continue_if_idle` nudge round.
4. Otherwise append the assistant `tool_calls` entry, partition calls into concurrency-safe batches vs serial singletons, execute via `Toolbelt.call_detailed`, append `role:"tool"` results, and record `on_step("tool", ...)`.

Defaults: `ModeLimits(max_rounds=20, max_tool_calls=40, max_tokens=0)` (`engine/modes/base.py`).

## Termination

A turn ends when: the model returns final text; the token cap is hit (`[预算]`); the tool-call cap is hit (`[中断]`); `LoopDetector` trips after one `LoopAdvisory` nudge round; the ReAct round cap is hit; or the deadline expires. Context overflow triggers one aggressive compact, `_emergency_truncate`, and a retry. A reply cut at the output cap that still carries tool calls fails closed: the calls are echoed back with `[未执行]` results so pairing holds and the model re-issues them whole.

Every llm step carries a `degraded` flag: quota / provider-failure placeholders are recorded rounds, not model output. The flag decides the close-out — a task turn that ended on degraded harness text is set `FAILED` with `RUN_FAILED` instead of `COMPLETED`, and a conversational turn still delivers its text but the reply-sink kind follows the same reading: degraded text delivers as an `error`, a harness wind-down (`[中断]` / `[预算]` / `[无工具可用]`) as a `warning`, everything else as a normal message.

`engine/turn.py:run_turn` then writes back the compacted history summary (`[历史压缩]` marker; wire entries the closing message was assembled from are excluded via the mode-reported delivery provenance, so nothing doubles up), appends the assistant reply, sets the terminal state — `WAITING_INPUT` for conversational instances, `COMPLETED` for tasks — and emits `AGENT_COMPLETED`.

Non-success exits: `run_turn` re-checks `CANCELLED` at entry, so an instance cancelled while queued for a concurrency slot stays cancelled. Hard cancellation records the terminal state and — conversational streaming only — persists the cancel-anchored partial assistant entry (`"\n\n…[已中断]"`) into history, so the next request contains what the user already saw on screen. `PauseRequested` sets `PAUSED` with a mid-turn checkpoint (task instances also keep the pending transcript for a live resume). The reply sink is success-only, so every non-success exit (pre-start cancel / cancel / pause / failure) closes the exchange with a best-effort `notice`/`error` chat message. `Master._turn` skips its persist step when the turn ended `CANCELLED`/`PAUSED` (there is no closing answer to record), and a stopped conversation revives on the next message; task instances stay terminal.

## Streaming

REACT and direct-chat rounds stream: `engine/modes/streaming.py` coalesces deltas (`DELTA_FLUSH_INTERVAL = 0.12` s, cancel anchor `"\n\n…[已中断]"`). Only conversational instances emit `agent.delta` events; other modes stay non-streaming.
