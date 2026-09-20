# Graph domain

English | [中文](graph.zh.md)

The `graph` domain builds and serves knowledge graphs: a canonical store written by code analysis and AI primitives, an index queue for repository ingestion, and pluggable engines (a C sidecar with a Python fallback).

Source: `packages/graph/src/graph/` — port 8030, enabled by default; `depends_on: ["sources"]` (the only non-empty `depends_on` among domains); store `data/runtime/graph/` (`graph.db`, `index.db`, `engine-python/`).

## Capabilities

`Registry("graph")` — 21 capabilities in three groups:

- Queue: `enqueue_index` (jails `repo_path` inside `workspace/`), `enqueue_l0`, `l0_view`, `cancel_index`, `reorder_queue`, `list_index_jobs`
- AI write primitives: `set_node`, `set_relationship`, `set_nodes`, `set_relationships`, `merge_nodes`, `graph_guide`
- Reads: `query_graph`, `get_subgraph`, `graph_stats`, `list_projects`, `engine_info`, `drop_project_graph`, `expand_neighbors`, `find_path`, `export_subgraph`

## Storage

`store.py` — `GraphStore` (SQLite `graph.db`): `nodes` (unique `(project, label, qualified_name)`) and `edges` (unique `(project, src, dst, type)`), each row carrying provenance `source` ∈ `code`/`ai`/`manual`. Coarse operations in `operations.py`, row/column helpers in `columns.py`.

`index_queue.py` — `IndexQueue` (SQLite `index.db`, `index_jobs`): priority queue with a status machine (`queued → running → done/failed/cancelled`), `level` (`l1` single-repo / `l0` cross-resource) and `kinds` columns added by `_migrate`.

## Engines

`engines/adapter.py` — `EngineAdapter` picks the engine per setting `graph.engine.mode` (`auto`/`c`/`python`):

- **C sidecar** — `engines/c/client.py` `CEngineClient` over HTTP, default `http://127.0.0.1:8123` (`graph.engine.c_url`; the sidecar itself reads `ENGINE_PORT`, default 9750, and `ENGINE_CACHE_DIR` → `data/graph-engine-cache/`).
- **Python fallback** — `engines/python/engine.py` `GraphEngine` with `engine_search`/`engine_query`/`engine_architecture` submodules and per-language indexers (`engines/python/indexer/`: python, jsts, markdown, regex-based fallbacks); data root `data/runtime/graph/engine-python/` plus `data/graph-db/`.

When the C engine is unavailable, the adapter publishes `graph.engine.fallback` on the bus.

## Pipelines

- `pipelines/code/analyze.py` — `analyze_repo`: engine index → export into the canonical store with `source="code"`, then automatic relation analysis.
- `pipelines/l0/relate.py` — `run_l0`: cross-resource relations, fetching sources via injected `call_sync("sources", "list_sources", ...)` — graph never imports sources.
- `pipelines/ai/guide.py` — validates AI-written nodes/relations.

## Scheduler

`scheduler.py` — `IndexScheduler` polls the queue, runs jobs under a concurrency semaphore (`graph.index.concurrency`, 1–4), retries with exponential backoff (`graph.index.max_attempts`), and emits `task.*` events.

## Settings

`graph.engine.mode`, `graph.engine.c_url`, `graph.index.concurrency`, `graph.index.max_attempts`, `graph.query.default_limit`.
