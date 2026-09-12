# Graph C engine (graph-engine)

This directory was migrated in from the MIT-licensed [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) as **vendored source** (not a runtime external dependency).  
Internal symbols uniformly use the `engine_*` / `ENGINE_*` prefixes (neutralized from upstream `cbm_*` / `CBM_*` during the migration); the external artifact is named **`graph-engine`**. Vendored third-party code (`internal/engine/vendored/`) is kept as shipped upstream.

## Capabilities

- HTTP: `/api/layout`, `/api/index`, `/api/index-status`, `/api/project-health`, `DELETE /api/project`, etc.
- JSON-RPC: `POST /rpc` (`tools/call`: `search_graph`, `get_graph_schema`, `trace_path`, etc.)
- **Excludes** the upstream React `graph-ui`; visualization is handled by Voyager `apps/web`

> The C engine only provides functional APIs (`/api/layout`, `/rpc`); frontend visualization is handled by Voyager `apps/web`. The asset_pack frontend asset serving has been removed.

## Build

Dependencies (WSL/Ubuntu example): `build-essential`, `make`, `zlib1g-dev`, `python3`.

**The Makefile entry point is `Makefile` (formerly `Makefile.rp`).**

Windows (WSL recommended):

```powershell
# From the repo root or this directory
.\services\graph_engine\graph_engine_core\scripts\build.ps1
```

Or:

```bash
cd packages/graph/src/graph/engines/c/core
# If the scripts were copied over from Windows, strip CRLF first: normalize with python or dos2unix scripts/*.sh
make -f Makefile -j$(nproc) graph-engine
# Artifact: build/c/graph-engine
```

## Run

When the C engine runs directly (not via the API), it reads `ENGINE_CACHE_DIR` / `ENGINE_ALLOWED_ROOT` (getenv inside the source):

```bash
export ENGINE_CACHE_DIR="<repo>/data/graph-engine-cache"
export ENGINE_ALLOWED_ROOT="<roots allowed for indexing>"
./graph-engine --ui=true --port=9750
```

The Voyager API integrates with it via environment variables (on the API side, `graph_engine_runtime/sidecar.py` translates the application-level `GRAPH_*` configuration into engine-level `ENGINE_*` at the boundary):

- `GRAPH_ENGINE_URL=http://127.0.0.1:9750`
- `GRAPH_ENGINE_BIN=<the executable built from this directory>`
- Optional: `GRAPH_CACHE_DIR` (graph SQLite cache root)

## License

See [`LICENSE`](LICENSE) in this directory (Copyright © 2025 DeusData, MIT) and [`THIRD_PARTY.md`](THIRD_PARTY.md).
