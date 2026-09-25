# agent — the agent runtime package (module map)

`src/agent` is the Python package body of the agent runtime: a resident process that watches the event stream and decides autonomously whether to act. The parent `agent/README.md` carries the package contract sections audited by `tests/docs/test_readme_contract.py`; this file only maps the code. Entry points: `python -m agent.main` (resident event loop) and `python -m agent.repl` (terminal console). Assembly order lives in `build.build_agent()`; the assembled product is `app.AgentApp`, shared by main, the REPL, and tests.

## Subpackages

| directory | role |
| --- | --- |
| capabilities/ | the agent's human-facing capability surface, registered into one `Registry("agent")` — see capabilities/README.md |
| mcp/ | external MCP server connections: pool, tool mounting, sessions, read-only service discovery — see mcp/README.md |
| context/ | context engineering: assembly, compression/pruning, on-demand loading, budgets, prefix-cache watch — see context/README.md |
| hooks/ | hook system: loading, trigger points, user-hook reload — see hooks/README.md |
| master/ | orchestration: arbitration, dispatch, task graph, blackboard, proactive outreach, sessions — see master/README.md |
| memory/ | profile/episodic/semantic/working memory plus retrieval, distillation, and the recorder — see memory/README.md |
| personas/ | persona presets loaded from `definitions/*.toml` — see personas/README.md |
| plugins/ | plugin discovery, approval, and declarative skill/hook loading — see plugins/README.md |
| policy/ | permission modes plus per-dimension gates (network / fs / app / shell) — see policy/README.md |
| runtime/ | event loop, scheduler with durable queue, meter/quota, trace, deadlines, recovery — see runtime/README.md |
| skills/ | skill loader (resident index, full text on demand), organizer, and the `builtin/` packs — see skills/README.md |
| subagent/ | spawn, per-run instances, user-built registry, execution modes — see subagent/README.md |
| tools/ | the agent's own tools (workspace / net / interact / self-management); group details in tools/README.md |

Each subpackage carries its own README; this file does not repeat their contents.

## Flat modules

| module | role |
| --- | --- |
| app.py | `AgentApp`: the dataclass holding handles to every in-process component |
| build.py | `build_agent()`: the composition root — assembly order and built-in tool registration |
| main.py | `python -m agent.main`: builds the agent and runs the resident event loop |
| repl.py | `python -m agent.repl`: console session routing input to `master.handle_user_message`, with local slash commands |
| contracts.py | Protocol layer decoupling tools / context / skills / subagent / master; keeps the static import graph acyclic |
| llm.py | `LLMClient` protocol and `FakeLLM` for tests and the no-key degradation path |
| llm_http.py | OpenAI-compatible chat-completions client for standalone runs; deliberately independent of `packages/llm` |
| llm_structured.py | schema validation, JSON repair/extraction, and structured completions with error-feedback retries |
| parity.py | frozen human/agent parity exception lists, read by the host parity test |
| settings.py | `agent.*` setting definitions; `user_only` security boundaries are marked here |

## Notes

- Import direction: the agent package must not import domain packages (enforced by import-linter; stated in the `llm_http.py` and `mcp/discovery.py` docstrings).
- Domain capabilities reach the agent through the host bridge under `domain__capability` names; this package stays unaware of domain implementations (see tools/README.md).
