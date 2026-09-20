# agent.tools — The agent's own tools

## Purpose

Internal tools that do not go through domain services: the agent's "hands and
feet" (workspace / net), interaction channels (interact), and self-management
(context / memory / skill / session / team / extension / observe). Domain
capabilities are wired in via `host.bridge` under `domain__capability` names;
this package remains unaware of domain implementations.

Directory discipline: **one tool per file, file name = tool
name**, with each file exporting a single factory `<name>_tool(...) -> AgentTool`;
mechanism files (jail / workdir / todo_store / question_broker) are
named by their mechanism responsibility; the group `__init__.py` does
zero-logic aggregation only. The shape is locked by
`agent/tests/granularity/test_file_granularity.py`.

```
core/        mechanism layer: AgentTool/Toolbelt (base), assembly-time source registry (registry),
             execution pipeline (invoke: validate→permissions→policy→write_roots confirm→hook→retry→circuit-break→result
             budget), result envelope (outcome), tiered activation (activate), agent
             self-capability binding (self_capability: via execute guard chain + audit)
workspace/   read · write · edit · grep · glob · bash · todowrite (set/query/update/delete);
             mechanisms: jail / workdir / todo_store
net/         web_fetch · web_search; outbound fetches are re-checked per hop
             against the shared platform_webguard guards (DNS pinning,
             redirect policy, bounded body read)
interact/    ask_user · request_context; mechanism: question_broker
context/     context (status/compact) — shares context.operations with the same-named
             human capability; mechanism: none
plan/        plan (status/write/enter/exit; the agent's exit submits for human
             review) · scratchpad; mechanism: plan_ops
memory/      memory (query/recall/remember/forget/clear)
skill/       skill (load/propose); mechanism: skill_ops
session/     session (list/create/fork/rename/delete/get/read/search/trace/pin/
             archive/set_active); mechanism: actions (shared dispatch + guard)
team/        subagent (spawn/list/register/unregister/wait/send) · agent_instance
             (cancel/pause/resume/checkpoints/abandon) · board (read/write) ·
             goal (get/create/set/status with driver rules)
extension/   extension (kind plugin/mcp/hook x list/install/uninstall/preview/reload)
observe/     observe (events/quota)
jobs/        jobs (list/reorder/cancel)
tools/       tools (list/describe/search)
```

## Configuration

The tools have no settings keys of their own; behavior is affected by
`agent.fs.*` (additional roots), `agent.network.*`, `agent.app.*`, and
`agent.context.tool_result_max` (result spillover), all hot-read.

## Extension Points

- Adding a built-in tool: create `tools/<group>/<name>.py` in the matching
  group, export `<name>_tool`, aggregate in the group `__init__.py`, and
  register it in `build.py`; if the human side should also have a same-named
  capability, put the implementation in `capabilities/<group>/<name>.py` and
  have the tool bind the same capability via
  `core/self_capability.capability_tool` (human and machine share the same
  source, audit symmetric);
- Governance-class tools must declare `write` / `irreversible` (drives the
  no-retry rule); permission reachability comes from the central R/D class
  table plus the `agent.permissions` modes (policy/permissions.py), and the
  only confirmation left is writes into user-configured write_roots;
- Exceptions (existing on one side only) must be registered in
  `agent/parity.py` with a written rationale, otherwise the parity freeze
  test goes red.

## Model Experience

- Tool names strictly match human-side capability names (`extension`, never a
  reordered name); descriptions are in Chinese and action-oriented;
- Call failure taxonomy (verbatim runtime markers): `[参数错误]` (parameter
  error — schema not satisfied, no side effects) → `[权限拒绝]` (rejected —
  the user's tool permission policy) → `[已拒绝]` (rejected — policy /
  guard) → `[已取消]` (cancelled — the write_roots confirmation declined) →
  `[已拦截]` (intercepted — circuit breaker) → `[工具失败]` (tool failure)
  (handler exception, including ServiceError messages);
- A conversation instance sees only the CORE activation set on its first turn
  (including `llm__get_usage_stats`); governance tools are activated on
  demand via `activate_tools(names=[...])`;
- Cost tiers: read-only tools with `concurrent_safe=True` can run in
  parallel; write tools get zero retries.

## Known Limitations

- `rename_session` / `delete_session` reject the user's current session
  outright (interaction contract); no override switch is provided;
- `read_events` reads whitelisted types only (agent.delta / agent.ask
  excluded);
- `bash` is not interpreted by a shell (no pipes/redirection); Windows
  built-in commands are unavailable.
