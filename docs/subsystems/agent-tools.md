# Agent tools

English | [中文](agent-tools.zh.md)

The tool surface: how tools are declared, composed into per-agent views, permissioned, and invoked. The full tool list with classes and actions is in [tool-catalog.md](../catalog/tool-catalog.md).

Source: `agent/src/agent/tools/`

## Tool model

`tools/core/model.py` — `AgentTool`: `name`, `description`, `handler`, `schema` (JSON Schema), `dimension` (fs/network/app/shell/skill), `write`, `irreversible`, `concurrent_safe`, `timeout_s`.

`tools/core/registry.py` — `ToolRegistry` merges named `ToolSource`s at assembly (later source wins; `origins()` tracks the owner). `tools/core/base.py` — `Toolbelt` holds the roster and derives views: `specs()`, `roster()`, `describe(name)`, `trimmed(allow)` (supports `prefix*` grants), `trimmed_read_only()`, `with_active(active, extra)` (graded activation), `with_policy(policy)`, plus `call()` / `call_detailed()`.

## Permissions

Two layers decide every call:

1. **`policy/permissions.py` `ToolPermissions`** — the agent-actor gate, reading setting `agent.permissions`: `{"mode": "full"|"no_dangerous"|"read_only", "deny": [...], "allow": [...]}`. Entries name a tool (`"bash"`), a tool action (`"session.delete"`), or a bash argv prefix (`"bash:git push"`, `"bash:git push *"` — the trailing `*` is optional and must stand alone as the final token; a pattern without it is still a prefix, so `git push` denies `git push origin main` too). Deny over-matches on purpose; the allow direction is stricter — an allow prefix covers only the command head, and an unmatched tail carrying a command boundary, substitution, or write-redirect withholds the allow (it falls through to the dangerous-class rejection). A command that parses to no argv tokens is denied outright when deny prefixes are configured, so malformed input cannot dodge a deny. `TOOL_CLASS` maps each tool to `R` (read-only) or `D` (dangerous); unknown tools classify as `D` (fail-closed), with documented action-level overrides (e.g. `session.delete`, `jobs.cancel`, `memory.forget`, `extension.install`). Legacy `agent.shell.denied` entries merge as bash deny prefixes.
2. **`policy/engine.py` `PolicyEngine`** — the dimension gate: `decide(Action(dimension, target, write, irreversible))` → `Decision`. Dimensions (`network.py`, `fs.py`, `app.py`, `shell.py`) hot-read their settings; levels are `L0` allow, `L1` notify, `L2` confirm. `L2` confirmation applies only when `decision.confirm_scope == "write_roots"` — a write into user-configured write roots goes through the ask-confirm callback; every other case proceeds directly with at most an `agent.policy.notify` event.

Filesystem roots: `agent.fs.read_roots` / `agent.fs.write_roots` fix the jail at assembly; fs tools additionally receive hot-read functions, so setting changes apply without restart.

## Invocation pipeline

`tools/core/invoke.py` — `invoke_tool` / `invoke_detailed`:

1. Find the tool; a miss yields close-match and unactivated-domain hints.
2. `validate_arguments` — one-level JSON-schema check.
3. `ToolPermissions.check` — mode/deny/allow gate.
4. `policy.decide(Action)` — dimension gate; possible outcomes: deny, L2 confirm (write_roots only), L1 notify, allow.
5. `pre_tool` hook — returning `False` blocks.
6. Handler with retry and a per-tool `CircuitBreaker`; writes and irreversible calls are never retried; timeouts and `ServiceError` are not retried.
7. Meter record (`MeterRecord(kind="tool", ...)`).
8. `post_tool` hook; result normalization to `ToolResult`; episodic recording.
9. Result budget — oversized results spill to `workspace/spill/` (`agent.context.tool_result_max` / `agent.context.tool_result_max_lines`). A spill write failure degrades to plain truncation; the spill-directory bound is separate best-effort housekeeping that never truncates an in-budget result.

## MCP tools

`mcp/` mounts external MCP servers (`agent.mcp.servers`, approval-gated): remote tools become `mcp__<server>__<tool>` agent tools (`mcp/mount.py`), `dimension="app"`, registered only after approval. `McpSession` (`mcp/session.py`) speaks JSON-RPC 2.0 over stdio or HTTP with a 30 s call timeout. Only server-answered JSON-RPC errors (`McpRpcError`) return as `[MCP 错误]` text; timeouts and transport failures propagate into the pipeline's retry and circuit breaker.

Consent is a persisted snapshot (`mcp/pool.py`): a user preview rebaselines the approved name set and writes it into the config entry (`consent` field), so the baseline survives restarts; a listing by an `AGENT` actor never rebaselines (a remote tool cannot widen its own surface). Startup reconnect and the periodic refresh mount only names seen at the last consent — cold state reads the snapshot from the config entry, and an entry without one mounts nothing until an explicit preview — while freshly appeared remote tools surface as `new_tools` and wait for the next preview. Servers reconnect and refresh concurrently; reconnects serialize on a pool-level connect lock and the session is read under the same lock hold. A stdio server is a process tree (a launcher shim begets grandchildren); on Windows the child is assigned a kill-on-close Job Object (`mcp/_win_job.py`) so close, shutdown, and this process's crash all reap the whole tree, degrading to direct-child-only termination when the assignment fails.

## Domain tool bridge

Host injects one tool per domain capability, named `<domain>__<capability>` (`packages/host/src/host/bridge.py`), executed through the full guard chain as actor `agent.main`. A curated subset is registered by default (e.g. `notes`, `graph`, `sources`, `settings__get_theme`); the rest activates on demand ([tool-catalog.md](../catalog/tool-catalog.md)).

## Parity

`agent/src/agent/parity.py` pins the human/agent parity contract: a capability exposed over REST is callable by the agent under the same `domain__capability` name; deviations are enumerated only in that module and checked by the host parity test (`test_parity_surface`).
