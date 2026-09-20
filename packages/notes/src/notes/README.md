# notes (src) — implementation of the notes domain

This directory holds the notes domain implementation: capability modules, the SQLite storage layer, and the assembly/entry points. The package-level contract (purpose, configuration, extension points, known limitations) lives in [packages/notes/README.md](../../../README.md); the subsystem walkthrough lives in [docs/subsystems/notes.md](../../../../docs/subsystems/notes.md). This file only maps what each file here contains.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `assets.py` | The `add_asset` capability plus controlled asset storage: content-addressed files under the workspace, served read-only via `/api/notes/assets/<id>`. |
| `batch.py` | Batch note actions (archive/unarchive/delete/export/pin/unpin) over up to 100 ids, with per-note failures recorded instead of aborting. |
| `capabilities.py` | Capability registry assembly: imports the per-concern modules so they register; exposes `Deps` / `init_deps` / `registry`. |
| `catalog.py` | Tags, backlinks, and stats capabilities: `list_tags` / `rename_tag` / `get_backlinks` / `notes_stats`. |
| `domain.py` | Leaf constant `DOMAIN = "notes"`, kept separate so `validate.py` and `store.py` avoid an import cycle. |
| `history.py` | Version history (`list_versions` / `read_version` / `restore_version`), `get_note_toc`, `resolve_links`, `edit_note_range`, `mark_note_span`. |
| `lifecycle.py` | Note CRUD and the trash flow: create/get/list/update/link, delete/restore/purge/empty_trash (with asset purge). |
| `marks.py` | `==tone:text==` highlight marks: parse/apply/strip/scan over Markdown bodies; no dependency on capabilities. |
| `mcp_server.py` | Exposes the registry as an MCP server over stdio (`python -m notes.mcp_server`). |
| `rest.py` | REST entry point: `create_app` / `app_factory`; thin HTTP shell around `wiring.wire`. |
| `runtime.py` | Module-level registry, `Deps` injection point, note lookup (`require_alive` / `get_any`), and `note.*` event emission. |
| `settings.py` | `SettingDef` list for `notes.*` keys (sorting, paging, autosave, trash retention, history depth, export directory, asset size cap, UI state). |
| `store.py` | `NoteStore`: the full storage layer — four state views, version snapshots, wiki-link persistence, escaped-LIKE search, PRAGMA-based column migration. |
| `store_links.py` | Wiki-link mechanics: `[[target]]` resolution (exact id, then case-insensitive title), `note_links` persistence, backlink queries. |
| `toc.py` | `extract_toc`: Markdown ATX heading outline with fenced-code skipping, matching the frontend semantics. |
| `transfer.py` | Markdown import/export with light front-matter, confined to the workspace jail. |
| `validate.py` | Field validation: title/content length limits, tag characters, import byte cap. |
| `view.py` | Notes-page UI state capability (`get/set_notes_view` under `notes.ui.*`, emits `notes.ui.changed`). |
| `wiring.py` | `wire()`: builds stores, injects deps, returns the assets router and the trash-retention start/stop; shared by standalone and host runs. |

## Entry points

- Standalone HTTP: `uvicorn notes.rest:app_factory --factory --port 8020` (per `rest.py` docstring); `create_app` wires and mounts the capability router plus the read-only assets router.
- Assembly: `wire()` in `wiring.py` is the single wiring source used both here and by `packages/host/`.
- MCP: `python -m notes.mcp_server` (requires `mcp>=1.0`).
