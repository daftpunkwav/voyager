# sources — sources domain implementation

Implementation of the sources domain: an aggregation shell over three self-contained submodules (repo / doc / web) plus the REST / MCP entry points. Package-level contract (tools, configuration, limitations) lives in [packages/sources/README.md](../../README.md); domain behavior is detailed in [docs/subsystems/sources.md](../../../../docs/subsystems/sources.md). This README is only a map of the files in this directory.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `capabilities.py` | Aggregate registry: merges the repo/doc/web sub-registries and serves the unified cross-kind stream (`list_sources` / `search_sources` / `sources_stats`) as pure fan-out plus merged sorting over the `STORES` map populated by `wiring.init_all`. |
| `files.py` | Read-only `/files/doc/{doc_id}` download router: paths resolved from the DB by id and confined to the stored location, media types mapped from the extension for browser inline preview. |
| `migration.py` | One-shot idempotent migration from legacy `books.db` / `news.db` to doc/web stores; migrated legacy files end up as `*.bak`, never deleted. |
| `settings.py` | `sources.*` setting definitions (`sources.sort.default`, `sources.import.clone`, `sources.doc.max_file_mb`). |
| `wiring.py` | Single assembly point for standalone (`rest.py`) and aggregate runs; composes the three module stores/queues; `clone_fn` / `parse_fn` are injectable hooks for tests and host `wire_extras`. |
| `rest.py` | Aggregate FastAPI shell (`uvicorn sources.rest:app_factory --factory --port 8010`) that mounts the read-only files router handed over by `wire`. |
| `mcp_server.py` | Stdio MCP entry point: `python -m sources.mcp_server` builds the server from `wire().registry`. |
| `modules/` | The submodules, each self-contained with its own store, queue, and `capabilities.py`: `repo/` (GitHub import: metadata, README, clone worker, [README.md](modules/repo/README.md)), `doc/` (document import, `extract.py` section extraction, parse worker), `web/` (URL clipping with resolve-and-pin SSRF guarding, manual page entry), `_shared/` (`text.py`: LIKE escaping and tag character rules), `_template/` (skeleton for new submodules, [README.md](modules/_template/README.md)). |

## Notes

- Submodules never import each other; the shell only merges them read-only, and adding a resource kind means one `STORES` registration with zero aggregate changes (`capabilities.py`).
- `_shared/` exists only to deduplicate conventions inside sources (its docstring explicitly rules it out as a general toolbox); cross-module communication does not flow through it.
