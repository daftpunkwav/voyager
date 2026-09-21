# Testing

English | [中文](testing.zh.md)

What is tested, where, and how the gates run.

## Python tests

Configured in the root `pyproject.toml`: `testpaths = ["packages", "agent"]`, importlib import mode, `asyncio_mode = auto`. Tests run with `uv run pytest -q` (part of `npm run test:py`).

| Location | Scope |
|---|---|
| `agent/tests/` | the largest suite: loop, tools, policy, context, subagents, memory, runtime machinery |
| `packages/host/tests/` | assembly, planning, wiring, parity (`test_settings_parity.py`, `test_parity_surface`) |
| `packages/platform/*/tests/` | framework packages |
| `packages/<domain>/tests/` | per-domain capabilities and stores |

## Frontend tests

- Unit: `apps/web/tests/unit/**/*.test.{ts,tsx}` under Vitest with jsdom (`tests/setup.ts` stubs browser APIs); `npm run test:web`.
- E2E: `apps/web/tests/e2e/` Playwright specs against the dev server (`E2E_PORT`, default 5193; `apps/web/playwright.config.ts`).

## Agent eval

`agent/tests/eval/` — scenario-based evaluation of turn behavior. `npm run eval` runs it (real-model scenarios are env-gated; the suite runs on fakes otherwise). `npm run eval:update` (`scripts/update_eval_baseline.py`) re-records the baseline; the baseline diff is the reviewable record of model-facing behavior change.

## Dependency graph check

`scripts/gen_dep_graph.py` regenerates the package dependency graph from the same imports `import-linter` checks; `npm run graph:check` fails when the committed graph is stale. The output is the bilingual pair `docs/catalog/module-graph.md` + `module-graph.zh.md` plus its `module-graph.i18n.yaml` consistency record.

## Running the gates

```sh
npm run gate        # gate:py && gate:web
npm run gate:py     # ruff + import-linter + mypy + pytest (branch coverage, ≥90% floor) + graph:check
npm run gate:web    # tsc + eslint + vitest + i18n keys + prettier
```

Gate failures are read directly from the command exit code; do not pipe gate commands through filters that swallow exit codes.
