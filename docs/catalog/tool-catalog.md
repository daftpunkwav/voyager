# Tool catalog

English | [中文](tool-catalog.zh.md)

The agent tool surface as registered at assembly. Declaration sites are authoritative; this page summarizes and links. Tool mechanics (permissions, invocation pipeline) are in [agent-tools.md](../subsystems/agent-tools.md).

## Builtin tools

| Tool | Declared in | Purpose |
|---|---|---|
| `read` / `write` / `edit` | `agent/src/agent/tools/workspace/` | file access inside the workspace jail |
| `glob` / `grep` | `agent/src/agent/tools/workspace/` | file search |
| `bash` | `agent/src/agent/tools/workspace/` | shell with cwd = workspace |
| `todowrite` | `agent/src/agent/tools/workspace/` | plan/todo list maintenance |
| `web_fetch` / `web_search` | `agent/src/agent/tools/net/` | outbound web, `dimension="network"` |
| `ask_user` | `agent/src/agent/tools/interact/` | human question/answer via the ask callback |
| `request_context` | `agent/src/agent/tools/interact/` | request page/workspace context from the frontend |
| `skill` | `agent/src/agent/tools/skill/skill.py` | load or propose skills (actions incl. `load`, `propose`) |
| `plan` | `agent/src/agent/tools/plan/plan_ops.py` | plan gate operations (late-bound) |
| `scratchpad` | `agent/src/agent/tools/plan/` | scratch notes |
| `context` | `agent/src/agent/tools/context/context.py` | LLM-facing context status and compaction |
| `activate_tools` | `agent/src/agent/tools/core/activate.py` | graded activation of dormant domain tools |

## Aggregated capability-backed tools

Each wraps one agent-registry capability (`tools/core/self_capability.py: capability_tool`), executed as actor `agent.main`:

| Tool | Declared in | Actions (examples) |
|---|---|---|
| `subagent` | `agent/src/agent/capabilities/team/subagent.py` | `spawn`, `list`, `register`, `unregister`, `wait`, `send` |
| `agent_instance` | `agent/src/agent/capabilities/team/` | instance inspect/cancel/abandon |
| `board` | `agent/src/agent/capabilities/team/` | blackboard notes |
| `goal` | `agent/src/agent/capabilities/team/goal.py` | per-session goal lifecycle |
| `memory` | `agent/src/agent/capabilities/memory/memory.py` | `query`, `recall`, `remember`, `forget`, `clear` |
| `extension` | `agent/src/agent/tools/extension/` | plugin approval/install/uninstall/reload |
| `session` | `agent/src/agent/capabilities/session/` | session management (incl. `delete`) |
| `observe` | `agent/src/agent/tools/observe/` | trajectory/log inspection |
| `jobs` | `agent/src/agent/tools/jobs/` | job list/cancel/reorder |
| `tools` | `agent/src/agent/tools/tools/tools.py` | tool catalog introspection (`describe_tool`, `list_tools`) |

## Domain tools

Host injects `<domain>__<capability>` tools for wired domains (`packages/host/src/host/bridge.py`), e.g. `notes`, `graph`, `sources`, `settings__get_theme`. A curated subset registers by default (`build.py` late-bound registrations: `plan_tools`, then `team_tools`/`memory_tools`/`extension_tools`/`session_tools`/`observe_tools`/`jobs_tools`/`tools_tools`); page-linked domains pre-activate through `_PAGE_PREACTIVATE` (`notes`, `graph`, `sources`); the rest activate via `activate_tools`.

## MCP tools

External MCP servers (`agent.mcp.servers`) mount their tools as `mcp__<server>__<safe-name>` (`agent/src/agent/clients/mount.py`), `dimension="app"`, registered only after user approval.

## Always-on set

`CORE_TOOLS` (`agent/src/agent/tools/core/activate.py`) is always activated: `ask_user`, `subagent`, `skill`, `memory`, `request_context`, `todowrite`, `read`, `write`, `edit`, `bash`, `grep`, `glob`, `settings__get_theme`, `settings__set_theme`, `activate_tools`, `context`, `session`, `llm__get_usage_stats`.

## Classification

`policy/permissions.py` `TOOL_CLASS` maps every tool to `R` (read-only) or `D` (dangerous); unknown tools are `D` (fail-closed). Action-level overrides mark specific actions `D` within otherwise read-only tools (e.g. `session.delete`, `jobs.cancel`, `memory.forget`, `extension.install`, `subagent.register`). The classification drives the `agent.permissions` modes (`full` / `no_dangerous` / `read_only`).
