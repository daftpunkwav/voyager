# packages/ agent rules

Working rules for coding agents touching any backend package. The family
table, port registry, and data-root semantics live in [README.md](README.md);
the architecture map lives in [docs/architecture.md](../docs/architecture.md).
This file is only the working conventions.

## Layout

- Domain packages sit at `packages/<domain>/` with the fixed shape:
  `pyproject.toml` (hatchling), `service.json` (module card, at the package
  root — the host scan reads it), `README.md`, `src/<domain>/`, and `tests/`
  (flat, no `__init__.py`; root pytest runs in importlib mode). The platform
  group has the same shape one level down: `packages/platform/<pkg>/src/platform_<pkg>/`.
- The import name equals the directory name (`from <domain>.rest import
  create_app`). A new member is not done until the root `pyproject.toml`
  lists it in `tool.uv.workspace.members`, `dependencies`, and
  `tool.uv.sources`, `uv sync` picks it up, and the port table in
  [README.md](README.md) has its number.

## Boundaries

- Dependency directions are fixed by `import-linter.ini` at the repo root:
  platform packages never import business layers (`platform-no-business`);
  domains never import each other (`domains-independent` — cross-domain only
  via capability calls or events); only the composition root imports domain
  wiring (`host-only-wiring`); aggregate submodules stay independent
  (`aggregate-submodules-independent`, `graph-pipelines-independent`). When
  `npm run lint:imports` fails, the change is wrong — do not weaken a
  contract to pass it.
- A domain's `pyproject.toml` declares `platform-*` dependencies only —
  never another domain. Consistency checks across domains belong in the
  consuming layer or the agent tests, not in cross-package imports.

## Domain surface

- A domain's REST surface comes from `src/<domain>/rest.py` (`create_app`
  factory) and its MCP surface from `src/<domain>/mcp_server.py`; each
  capability name registered in `src/<domain>/capabilities.py` becomes the
  agent tool name `<domain>__<capability>` through the host bridge —
  renaming a capability is a breaking change to the tool roster.
- Long tasks enqueue a `JobRef` and report progress through the event stream;
  handlers never block on completion.
- The module card `service.json` controls discovery and mounting
  (`enabled_by_default`, port). The gateway mounts the domains the card
  declares; no host edit is needed to add a domain.

## Data

- Standalone runs write to `packages/<domain>/data/` (gitignored,
  self-contained); the aggregated run injects the shared `data/runtime/`
  root. The two forms are disjoint by design — do not write code that reads
  across them, and never commit either directory's contents.
- Every store's location and retention are cataloged in
  [docs/catalog/data-layout.md](../docs/catalog/data-layout.md); a storage
  change updates that catalog in the same change.
