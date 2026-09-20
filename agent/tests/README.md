# tests — the agent package test suite

> Language: **English** | [简体中文](README.zh.md)

Pytest suite for `agent/src/agent`, run from the repository root: `npm run test:py` (which invokes `uv run pytest -q`); the evaluation subset runs on its own via `npm run eval`. `conftest.py` provides assembled-app fixture helpers (`agent_replies`, `settle`); `__init__.py` anchors the package so pytest's importlib mode does not shadow the installed `agent` package.

## Layout

Flat `test_*.py` files at the root cover cross-cutting surfaces: wiring, capabilities, clients (plus resilience), hooks, plugins, personas, policy (plus notify), repl (plus replay), skills, mcp, redaction, streaming UX, the LLM clients (http / multimodal / structured), user-hook reload, naming neutrality (brand literals in source), and the module docstring header style.

Subdirectories mirror the package (selected themes, not exhaustive listings):

- context/ — context engineering: builder, editor, budgets, pruning, prefix cache, plan gate, tokenizer
- master/ — arbitration, dispatch surface, task graph, goal, sessions, proactive outreach, resilience
- memory/ — memory kinds, distillation, recorder, read policy, vector store (including degradation)
- runtime/ — event loop, scheduler and queue store, meter, trace spans, recovery, deadlines, budgets
- policy/ — permission modes, shell policy, write-roots confirmation
- skills/ — the organizer
- subagent/ — modes, checkpoints and resume, pause/cancel, instance usage, registry
- tools/ — tool surface: registry, search, edit matchers, web search/fetch, AskUser, result budgets, plus per-group cases (extension / memory / observe / session / team)
- eval/ — behavior baseline: `test_eval_scenarios.py` replays fixed task scenarios on FakeLLM scripts, fully offline; `npm run eval` compares against `baseline.json` and `npm run eval:update` regenerates it after deliberate behavior changes
- granularity/ — file-granularity audit: one tool per file under `tools/<group>/`, one capability per file under `capabilities/<group>/`, file name = product name; mechanism and aggregation files sit in frozen allowlists
- docs/ — README contract audit: enumerated package READMEs must carry the required contract sections

## Real-model evaluation

`eval/test_eval_real.py` drives the same scenario style against a live OpenAI-compatible endpoint and is skipped unless `AGENT_EVAL_BASE_URL`, `AGENT_EVAL_API_KEY`, and `AGENT_EVAL_MODEL` are set; assertions stay behavioral and model-agnostic.
