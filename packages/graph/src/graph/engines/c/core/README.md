# Graph C engine (graph-engine)

This directory was migrated in from the MIT-licensed [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) as **vendored source** (not a runtime external dependency).  
Internal symbols uniformly use the `engine_*` / `ENGINE_*` prefixes (neutralized from upstream `cbm_*` / `CBM_*` during the migration); the external artifact is named **`graph-engine`**. Vendored third-party code (`internal/engine/vendored/`) is kept as shipped upstream.

## Capabilities

- HTTP: `/api/index`, `/api/index-status`, `/api/project-health`, `DELETE /api/project`
- JSON-RPC: `POST /rpc` (`tools/call`: `search_graph`, `get_graph_schema`, `trace_path`, etc.)
- **Excludes** the upstream React `graph-ui`; visualization is handled by Voyager `apps/web` (the asset_pack frontend asset serving has been removed)

## Build

Dependencies (WSL/Ubuntu example): `build-essential`, `make`, `zlib1g-dev`, `python3`.

Windows (WSL recommended):

```powershell
# From the repo root or this directory
.\packages\graph\src\graph\engines\c\core\scripts\build.ps1
```

Or:

```bash
cd packages/graph/src/graph/engines/c/core
# If the scripts were copied over from Windows, strip CRLF first: normalize with python or dos2unix scripts/*.sh
make -f Makefile -j$(nproc) graph-engine
# Artifact: build/c/graph-engine
```

## Run

When the C engine runs directly, it reads `ENGINE_CACHE_DIR` / `ENGINE_ALLOWED_ROOT` (getenv inside the source):

```bash
export ENGINE_CACHE_DIR="<repo>/data/graph-engine-cache"
export ENGINE_ALLOWED_ROOT="<roots allowed for indexing>"
./graph-engine --ui=true --port=9750
```

To point the Voyager API at a running sidecar, set the `graph.engine.c_url`
setting (default `http://127.0.0.1:8123`) to the engine's actual address —
the engine's own default port is 9750, so pass `--port=8123` (or change
`graph.engine.c_url`) to make the two meet. The sidecar is **not started
automatically**: start it manually before switching `graph.engine.mode` to
`c`; in `auto` mode the API falls back to the built-in Python engine when
the health probe fails.

## License

See [`LICENSE`](LICENSE) in this directory (Copyright © 2025 DeusData, MIT) and [`THIRD_PARTY.md`](THIRD_PARTY.md).
