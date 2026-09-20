# graph — knowledge-graph domain implementation

Implementation of the graph domain: a canonical graph store, an index-job queue and scheduler, C/Python dual engines, and the code / L0 / AI pipelines that fill the graph. Package-level contract (tools, configuration, limitations) lives in [packages/graph/README.md](../../README.md); domain behavior is detailed in [docs/subsystems/graph.md](../../../../docs/subsystems/graph.md). This README is only a map of the files in this directory.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `capabilities.py` | Capability registry and `Deps`: queue operations (`enqueue_index` / `enqueue_l0` / `cancel_index` / `reorder_queue` / `list_index_jobs`), write primitives (`set_node` / `set_relationship`; `source` is recorded as `ai` for agent actors and `manual` for user actors), reads (`query_graph` / `get_subgraph` / `graph_stats` / `engine_info`, plus the L0 and project views); all reads go through the store, never directly to engines. |
| `columns.py` | Column constants for the nodes/edges tables plus row-to-dict helpers, shared by store and operations to avoid circular imports. |
| `store.py` | Canonical SQLite graph store keyed by the natural key `(project, label, qualified_name)`; read primitives and provenance tracking (`source` = "code" / "ai" / "manual"); delegates coarse operations to `operations.py`. |
| `operations.py` | Coarse-grained read/maintenance operations on a `GraphStore`: neighbor traversal, `find_path`, `merge_nodes`, `export_subgraph`. |
| `index_queue.py` | Persistent SQLite priority queue for index jobs: enqueue / cancel / reorder, the `queued→running→done/failed/cancelled` state machine, and `level="l1"` (deep single-resource) vs `level="l0"` (cross-resource) job levels. |
| `scheduler.py` | `IndexScheduler`: polls the queue under a concurrency semaphore, retries with exponential backoff up to an attempts cap, emits `task.progress` / `task.completed` / `task.failed` on the bus. |
| `settings.py` | `graph.*` setting definitions (`graph.engine.mode`, `graph.engine.c_url`, `graph.index.concurrency`, `graph.index.max_attempts`, `graph.query.default_limit`) and `DEFAULT_C_URL`, the single source for the C sidecar address. |
| `wiring.py` | Composition root shared by standalone (`rest.py`) and aggregated (`packages/host/`) runs; injects the late-bound `call_sync` used by the L0 pipeline — graph never imports the sources package. |
| `rest.py` | Thin FastAPI shell; run standalone with `uvicorn graph.rest:app_factory --factory --port 8030`. |
| `mcp_server.py` | Stdio MCP entry point: `python -m graph.mcp_server` builds the server from `wire().registry`. |
| `engines/` | Engine layer: `adapter.py` prefers the C engine, falls back to the in-process Python engine, and publishes `graph.engine.fallback`; `c/` holds the sidecar client (`client.py`), the 3-D layout module (`layout/`), and the vendored C core (see [engines/c/core/README.md](engines/c/core/README.md)); `python/` holds the Python fallback engine (store, search, Cypher subset, architecture surface, layout, indexer, optional HTTP sidecar `server.py`). |
| `pipelines/` | Pipeline implementations, one directory each: `ai/guide.py` (label/type vocabularies, validation, and `guide_text()` guidance for agent-built graphs), `code/` (`analyze.py` runs engine indexing and exports into the store; `relate.py` writes cross-repo dependency edges), `l0/relate.py` (cross-resource relation graph built from the resource inventory via the injected `call_sync`). Pipeline directories do not import each other. |

## Entry points

- HTTP: `rest.py` (`create_app` / `app_factory`); MCP: `mcp_server.py`; embedding: `wiring.wire(data_dir, ...) -> Wiring`.
- Job flow: `capabilities.enqueue_index` → `index_queue` → `scheduler` → `pipelines.code.analyze` (which chains `pipelines.code.relate` internally), with engine calls behind `engines.adapter`.
