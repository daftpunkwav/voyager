# scripts/ — Repository maintenance scripts

> Language: **English** | [简体中文](README.zh.md)

Small Python utilities for repository maintenance. They are invoked through the repository-root `package.json` npm scripts shown below, or directly with `uv run python scripts/<name>.py`.

## Scripts

| Script | Invoked by | Responsibility |
| --- | --- | --- |
| `bootstrap_readmes.py` | — (no npm script) | One-shot generator that writes contract-style README skeletons with fixed sections (Purpose, Configuration, Extension Points, Model Experience, Known Limitations, ...) for the backend package and agent directories listed in its internal `CONTENT` table; it skips files that already contain the `## Purpose` and `## Known Limitations` sections. |
| `gen_dep_graph.py` | `npm run graph` | Regenerates `docs-local/arch-diagrams/module-graph.md` — a mermaid dependency graph built with grimp from the `root_packages` declared in `import-linter.ini` (direct imports aggregated per top-level package, sorted output). With `--check` (exposed as `npm run graph:check`) it exits 1 when the file is missing or stale. |
| `update_eval_baseline.py` | `npm run eval:update` | Regenerates the agent evaluation baseline: it runs every scenario from `agent/tests/eval/test_eval_scenarios.py` and rewrites the baseline JSON referenced by that module. |

## Notes

- `scripts/` is covered by the Python formatting/linting gate (`npm run lint:py` runs ruff format and check over `packages agent scripts`); mypy (`typecheck:py`) and pytest (`test:py`) target `packages` and `agent` only.
- `gen_dep_graph.py` requires `grimp`, available in the uv environment.
