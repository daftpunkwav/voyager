# capabilities — the agent's human-facing capability surface

One capability per file under `capabilities/<group>/<name>.py`: the file name is the capability name, and each file holds one `@capability` definition plus a `register(reg, deps)` binder. These are the capabilities a human calls through REST; same-named agent tools bind the same operations (one implementation, two drivers). The tool side lives in `tools/` — see tools/README.md; capabilities deliberately without an agent tool are enumerated in the parity exception list (`../parity.py`).

The entry point is `build_agent_registry(deps)` in `registry.py`, called by `build.py` with a `CapabilityDeps` container; `registry.py` itself holds zero logic — import order only.

## Contents

| group | files | role |
| --- | --- | --- |
| context | context.py | context-window management (status / compact) on the same engine operations as the agent's context tool |
| extension | extension.py; add_mcp_server.py, approve_mcp_tools.py, remove_mcp_server.py, set_plugin_approval.py | plugin / external MCP / user-hook surface; the four named files are effectively user-only privilege boundaries |
| interact | answer_question.py, report_page_context.py | human-to-agent channels: AskUser answers and frontend page-context pushes (human-only by direction) |
| jobs | jobs.py | background tasks as the model/human sees them: list / reorder / cancel |
| memory | memory.py, rate_turn.py | memory query / recall / remember / forget / clear; user ratings of finished turns |
| observe | observe.py, list_personas.py | operational self-observation (events / quota); the persona catalog (no agent tool) |
| plan | plan.py | session plan gate: status / write / enter / exit |
| session | session.py | chat-session management: list / create / fork / rename / delete / get / read / search / trace / pin / archive / set_active |
| settings | get_settings.py, set_setting.py | full settings schema read; single-setting write |
| skill | skill.py, list_skills.py | skill load / propose; the resident skill index (no agent tool) |
| team | subagent.py, agent_instance.py, board.py, goal.py | subagent spawn / list / register / unregister / wait / send; instance cancel / pause / resume / checkpoints / abandon; task-scoped shared blackboard; durable session goal |
| tools | tools.py | tool-roster self-management: list / describe / search |
| workspace | todowrite.py | plan surface: query / set / update / delete, per chat session or global |

## Notes

- `deps.py` defines `CapabilityDeps`, a single dataclass injected by `build.py` on every registry build; its docstring forbids splitting it into fields or module-level globals.
- `tests/granularity/test_file_granularity.py` locks this layout: one capability per file, file name = capability name, `register(reg, deps)` binder, with mechanism and aggregation files in frozen allowlists.
