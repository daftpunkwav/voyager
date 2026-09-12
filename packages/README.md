# packages — Backend modules root

platform (cross-cutting mechanisms) + domain packages (independently runnable processes) + host (composition root).

Each domain directory = an independently runnable process (§13.1): it ships its own registry → REST + MCP, and its tests only run within its own directory.
Adding a domain = copy `_template`, write the `service.json` module card, touch no other directory —
after a restart the host scan picks it up automatically (`packages/host/src/host/scan.py` reads the card and assembles it), and `<domain>__*` shows up in the agent tool roster.

Standalone run: each domain's `rest.py` exposes the `create_app` factory,
`uvicorn <domain>.rest:app_factory --factory --port <port from the table below>`;
MCP: `python -m <domain>.mcp_server` (members are installed editable, runnable from any directory).

## In-package layout (src layout)

```
packages/<domain>/
├── pyproject.toml     # hatchling; dependencies declare platform-* only
├── service.json       # module card (the host scan reads this; not inside src)
├── README.md
├── src/<domain>/      # import name = directory name: from <domain>.rest import create_app
└── tests/             # flat, no __init__.py (root pytest runs in importlib mode)
```

- The platform group has the same shape: `packages/platform/<pkg>/src/platform_<pkg>/`;
- All members are installed into the venv as editable by `uv sync`, with no sys.path injection anymore;
- A new domain must also be added to the root `pyproject.toml` members / dependencies / tool.uv.sources;
- Decision and migration records: docs-local/design/2026-09-10-packages-src-layout.md.

## Data roots (dual-track semantics, intentional)

- **Standalone run**: data is written by default inside the domain directory, `packages/<domain>/data/`
  (self-contained, the whole directory can be deleted; listed in .gitignore to prevent accidental commits);
- **Aggregated run** (packages/host as composition root, the everyday form): a shared `data/runtime/` singleton is injected,
  under the same root as the agent/event stream; the agent workspace lives at `data/workspace/`.
  Data in the two forms is disjoint; an empty database after switching back to a standalone run is expected, not data loss.

## Port registry (single registry; new services claim a number here)

| Port | Service   | Status      |
| ---- | --------- | ----------- |
| 8000 | gateway   | implemented |
| 8010 | sources   | implemented |
| 8020 | notes     | implemented |
| 8030 | graph     | implemented |
| 8040 | office    | implemented |
| 8050 | code-exec | implemented |
| 8060 | browser   | implemented |
| 8070 | llm       | implemented |
| 8080 | settings  | implemented |
| 8090 | _template | example     |

## Legacy layout migration (completed)

- The old `services/api`, `services/agent`, `services/graph_engine`, and `services/mcp`
  became `gateway`, top-level `agent/`, `graph`, and each domain's own `mcp_server.py` respectively;
- 2026-09-06 three source roots consolidated: top-level `services/` → `packages/`, `platform/` →
  `packages/platform/`, `deploy/` → `packages/host/`, TS shared config →
  `apps/config/`, `workspace/` → `data/workspace/`, `runtime-data/` →
  `data/runtime/` (see docs-local/design/2026-09-06-three-source-roots.md);
- 2026-09-10 src layout: each member's sources moved from flat at the package root into `src/<name>/`, the import prefix
  `packages.<x>` retired in favor of `<x>`, and members switched from virtual to editable installs
  (see docs-local/design/2026-09-10-packages-src-layout.md).
