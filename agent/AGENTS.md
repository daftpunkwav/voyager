# agent/ agent rules

Working rules for coding agents in the agent source root. The package contract
(owner: README.md, config: settings.py) and the per-subsystem READMEs under
`src/agent/` describe what the code does; this file is only the working
conventions.

## Layout

- Sources live in `src/agent/`, tests in `tests/`. The package is a uv
  workspace member installed editable; imports use the `agent.` prefix from
  anywhere in the venv.
- Layering law: the agent never imports domains, the gateway, or the
  composition root (the `agent-no-domain` contract in `import-linter.ini`).
  Domain capabilities reach the agent through the host bridge as
  `domain__capability` tools; this package stays unaware of domain
  implementations.

## File discipline

- One tool per file under `src/agent/tools/<group>/`, file name = tool name,
  each file exporting a single `<name>_tool(...)` factory; one capability per
  file under `src/agent/capabilities/<group>/` under the same rule. Mechanism
  files are named by their mechanism responsibility; group `__init__.py`
  files do zero-logic aggregation only. The shape is locked by
  `tests/granularity/test_file_granularity.py`.
- Python files open with a pure module docstring (no `@file` tags); the style
  is enforced by `tests/test_file_header_style.py`. Comments and docstrings
  are English.

## Parity and frozen surfaces

- Human-facing capabilities and agent tools share one name and one
  implementation (`extension` is one capability file and one same-named tool
  file, never a reordered name); a same-named pair
  binds through `tools/core/self_capability.py`. Exceptions are registered in
  `src/agent/parity.py` with a rationale, or the parity test goes red.
- `tests/test_capabilities.py` freezes the capability name roster. Adding a
  capability or tool means: create the file, aggregate it in the group
  `__init__.py`, register it in `build.py` (tools) or the capability
  registry, then update the frozen test expectation in the same change.

## Tests

- Flat test files at `tests/` top level plus per-area subdirectories
  (`context/`, `engine/`, `memory/`, `orchestrator/`, `policy/`, `runtime/`,
  `sessions/`, `skills/`, `tools/`, `eval/`, `granularity/`, `docs/`). Run with the root
  gate (`npm run test:py`); the eval suite (`tests/eval/`) runs offline via
  `npm run eval`, and its real-model cases are env-gated.
- Settings-driven behavior is expressed through `agent.*` keys declared in
  `src/agent/settings.py`; tests set keys through the settings framework, not
  by patching private attributes.
