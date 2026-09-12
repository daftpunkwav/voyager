# agent.tools — The agent's own tools

## Purpose

Internal tools that do not go through domain services: the agent's "hands and
feet" (workspace / net), interaction channels (interact), and self-management
(context / memory / skill / session / team / extension / observe). Domain
capabilities are wired in via `host.bridge` under `domain__capability` names;
this package remains unaware of domain implementations.

Directory discipline (task brief §4.4): **one tool per file, file name = tool
name**, with each file exporting a single factory `<name>_tool(...) -> AgentTool`;
mechanism files (jail / workdir / todo_store / net_guard / question_broker) are
named by their mechanism responsibility; the group `__init__.py` does
zero-logic aggregation only. The shape is locked by
`agent/tests/granularity/test_file_granularity.py`.

```
core/        mechanism layer: AgentTool/Toolbelt (base), assembly-time source registry (registry),
             execution pipeline (invoke: validate→policy→confirm→hook→retry→circuit-break→result
             budget), result envelope (outcome), tiered activation (activate), agent
             self-capability binding (self_capability: via execute guard chain + audit)
workspace/   read_file · write_file · edit_file · list_dir · delete_file · grep · glob · run_shell ·
             todo_write · todo_read; mechanisms: jail / workdir / todo_store
net/         web_fetch · web_search; mechanism: net_guard (DNS/intranet resolution guard)
interact/    ask_user · request_context; mechanism: question_broker
context/     context_status · compact_context (shares context.operations with same-named
             human-side capabilities)
memory/      recall_memory · get_memory · clear_memory · set_profile · delete_profile
skill/       load_skill
session/     session_list · session_create · session_fork · rename_session · delete_session · read_history
team/        spawn_subagent · cancel_run · resume_run · register_subagent · list_subagents ·
             list_resumable_checkpoints · abandon_resumable_checkpoint
extension/   list_plugins · install_plugin · uninstall_plugin · list_mcp_servers · preview_mcp_tools ·
             reload_user_hooks · list_user_hooks
observe/     read_events · get_resource_quota · list_tools
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
- Governance-class tools must declare `write` / `irreversible`, tiered by
  policy (L1 notify / L2 confirm);
- Exceptions (existing on one side only) must be registered in
  `agent/parity.py` with a written rationale, otherwise the parity freeze
  test goes red.

## Model Experience

- Tool names strictly match human-side capability names (`install_plugin`,
  not `plugin_install`); descriptions are in Chinese and action-oriented;
- Call failure taxonomy (verbatim runtime markers): `[参数错误]` (parameter
  error — schema not satisfied, no side effects) → `[已拒绝]` (rejected —
  policy / guard) → `[需确认]` / `[已取消]` (needs confirmation / cancelled,
  L2) → `[已拦截]` (intercepted — circuit breaker) → `[工具失败]` (tool
  failure)
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
- `run_shell` is not interpreted by a shell (no pipes/redirection); Windows
  built-in commands are unavailable.

## Deferred Work

- Phase 21: `run_shell` routes to the code_exec domain (unified execution
  channel); `net_guard` moves to `platform_webguard`;
- Phase 19: the `jobs/` group (list_jobs / cancel_job) and
  `interact/reach_out`;
- Phase 20: `team/read_board` / `write_board`.
