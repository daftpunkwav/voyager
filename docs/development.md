# Development

English | [中文](development.zh.md)

Toolchain, startup, and repository conventions.

## Toolchain

- Python 3.11 (`.python-version`), managed with [uv](https://docs.astral.sh/uv/). The repo is a uv workspace (`[tool.uv.workspace]` in the root `pyproject.toml`) with 20 editable members: `agent`, 11 `packages/*` (10 domains plus `_template`), and 8 `packages/platform/*`. All are src-layout hatchling packages; `uv sync` installs everything editable plus dev tools (`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `import-linter`).
- Node ≥ 20.11 (`.nvmrc`: 20), npm 10 workspaces (`apps/*`). Frontend deps in `apps/web/package.json`.
- Ruff (line length 100, isort), mypy (pydantic plugin, `mypy_path` covers every `src` root), import-linter (`import-linter.ini`).

## Running

- One command: `uv run python -m host.dev` — backend (`host.assemble:build`) on `127.0.0.1:8000` plus the Vite dev server on `127.0.0.1:5173`; both stop together (Ctrl+C).
- Backend only: `uv run uvicorn host.assemble:build --factory --port 8000`.
- Frontend only: `cd apps/web && npm run dev` (proxies `/api` to 8000).
- Standalone domain: `uv run uvicorn <domain>.rest:app_factory --factory --port <port>` (ports in each `service.json`); standalone MCP: `uv run python -m <domain>.mcp_server`.

## Gates

| Script | Runs |
|---|---|
| `npm run lint:py` | `ruff format --check` + `ruff check` over `packages agent scripts` |
| `npm run lint:imports` | `lint-imports --config import-linter.ini` |
| `npm run typecheck:py` | `mypy packages agent` |
| `npm run test:py` | `pytest -q` |
| `npm run graph:check` | regenerates and diffs the dependency graph (`scripts/gen_dep_graph.py --check`) |
| `npm run gate:py` | all of the above |
| `npm run gate:web` | `tsc --noEmit` + `eslint --max-warnings 0` + `vitest run` + i18n key check + `prettier --check` |
| `npm run gate` | `gate:py && gate:web` |
| `npm run eval` | agent eval suite (`agent/tests/eval`), env-gated for real models; `eval:update` re-records the baseline |

Pre-commit (husky + lint-staged) formats and lints `apps/web/src/**/*.{ts,tsx}` and blocks committing `.env`/`.env.local`.

## Conventions

- Commit subjects: `<type>(<scope>): <subject>` with type ∈ `feat/fix/refactor/chore/docs/test/perf`.
- Python file headers are pure module docstrings (no `@file` tags); TypeScript/CSS use `/** @file */`.
- Code comments and docstrings in English; UI strings via i18n (`zh-CN` is the source locale).
- New domain: copy `packages/_template/` (procedure in its README), add the member to the root `pyproject.toml` workspace/deps, drop a `service.json` — no host edit needed.
- Platform constraint changes run through `import-linter.ini` contracts: `platform-no-business`, `domains-independent`, `host-only-wiring`.
