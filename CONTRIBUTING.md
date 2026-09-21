# Contributing

> Language: **English** | [简体中文](CONTRIBUTING.zh.md)

This guide is the onboarding layer for contributors. It points at the
single-source documents; when prose and code disagree, the code and the gate
scripts win.

## Environment

- Python 3.11 (`.python-version`) managed with [uv](https://docs.astral.sh/uv/);
  the repo is a uv workspace with every member installed editable (`uv sync`
  also installs ruff, mypy, pytest, and import-linter).
- Node ≥ 20.11 (`.nvmrc`: 20) and npm 10 workspaces (`apps/*`).
- Configure the repo-root `.env` (never committed). `SECRETS_ENCRYPTION_KEY`
  (or the fallback name `SECRET_KEY`) must be a long random string — the
  documented sample values are rejected. Backend environment variables are
  documented in `.env.example`; a few frontend-only variables
  (`VITE_API_TARGET`, `E2E_PORT`) are read from the shell instead.
- Start everything with `uv run python -m host.dev` (gateway on 8000, Vite on
  5173). See [docs/development.md](docs/development.md) for the per-process
  variants.

## Workflow

1. Branch from `main` as `<type>/<kebab-case-description>`, e.g.
   `fix/chat-history-paging`.
2. Commit with `<type>(<scope>): <subject>` where type is `feat`, `fix`,
   `refactor`, `chore`, `docs`, `test`, or `perf`. One commit carries one
   concern; keep every diff traceable to its request.
3. Do not refactor unrelated code in passing. The full conventions live in
   [AGENTS.md](AGENTS.md); subtree conventions live next to the code
   ([agent/](agent/AGENTS.md), [packages/](packages/AGENTS.md),
   [apps/web/](apps/web/AGENTS.md)).

## Before you push: quality gates

GitHub Actions runs the gates on every push and pull request
([.github/workflows/ci.yml](.github/workflows/ci.yml)); a red gate there
blocks the merge. Run them locally as well before every push and confirm a
green exit code directly (do not infer it from a pipe):

```bash
npm run gate        # gate:py && gate:web
npm run eval        # agent eval suite (agent/tests/eval); env-gated for real models
```

`gate:py` = ruff format/check, import-linter layering contracts, mypy,
pytest, dependency-graph check. `gate:web` = tsc, eslint (`--max-warnings 0`),
vitest, i18n key check, prettier. What each script runs:
[docs/development.md](docs/development.md). A red gate means fix the change —
do not weaken a check to pass it.

## Tests

- Placement: each package's tests live in its own `tests/` (flat, no
  `__init__.py`); agent tests live in `agent/tests/` (including the
  granularity audit and the eval harness). Layout and gates:
  [docs/testing.md](docs/testing.md).
- A behavior change updates or adds the test that pins that behavior; a bug
  fix lands with a regression test.
- The agent test suite includes frozen-surface tests (capability/tool name
  parity, file granularity, file headers, naming neutrality). When a test
  there goes red, the fix is in the change, not in the frozen list — new
  surfaces are registered explicitly, per the rules in
  [packages/AGENTS.md](packages/AGENTS.md) and [agent/AGENTS.md](agent/AGENTS.md).

## Docs and copy

- A behavior change updates the documentation in the same change. The `docs/`
  tree mirrors the code bilingually (three files per document; the pairing
  contract is [docs/AGENTS.md](docs/AGENTS.md)). Package READMEs follow the
  contract in [packages/README.md](packages/README.md).
- Documentation faces the code: current state, verifiable claims, no plan or
  report references.
- Code comments and docstrings are English. User-visible UI copy lives in the
  i18n resources (`apps/web/src/i18n/resources/`), with `zh-CN` as the source
  locale and `en` mirrored — never inline.

## Submitting

- One concern per change, gates green, and the behavior delta described in the
  commit body. New domains follow the `packages/_template/` procedure
  (copy the template, add the workspace member, drop a `service.json` — no
  host edit needed).
- Extension points per package are listed in that package's `README.md`
  (start from [packages/README.md](packages/README.md)).

## Security

Do not open public issues for vulnerabilities. Report privately per
[SECURITY.md](SECURITY.md).

## License

The project is licensed under the [MIT license](LICENSE); by contributing you
agree that your contributions are licensed under it as well.
