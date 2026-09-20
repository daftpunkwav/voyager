# packages — Backend modules root

platform (cross-cutting mechanisms) + domain packages (independently runnable processes) + host (composition root).

Each domain directory = an independently runnable process: it ships its own registry → REST + MCP, and its tests live inside its own directory.
Adding a domain = copy `_template`, write the `service.json` module card, and register the workspace member — no host edit needed —
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
- All members are installed into the venv as editable by `uv sync`, with no sys.path injection;
- A new domain must also be added to the root `pyproject.toml` members / dependencies / tool.uv.sources;

## Data roots (dual-track semantics, intentional)

- **Standalone run**: data is written by default inside the domain directory, `packages/<domain>/data/`
  (self-contained, the whole directory can be deleted; listed in .gitignore to prevent accidental commits);
- **Aggregated run** (packages/host as composition root, the default form): a shared `data/runtime/` singleton is injected,
  under the same root as the agent/event stream; the agent workspace lives at `data/workspace/`.
  Data in the two forms is disjoint; an empty database after switching back to a standalone run is expected, not data loss.

## Port registry (single registry; new services claim a number here)

| Port | Service   |
| ---- | --------- |
| 8000 | gateway   |
| 8010 | sources   |
| 8020 | notes     |
| 8030 | graph     |
| 8040 | office    |
| 8050 | code-exec |
| 8060 | browser   |
| 8070 | llm       |
| 8080 | settings  |
| 8090 | _template |

Engineering conventions for this tree: [AGENTS.md](AGENTS.md).
