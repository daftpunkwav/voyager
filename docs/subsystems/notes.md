# Notes domain

English | [中文](notes.zh.md)

The `notes` domain is the knowledge base: Markdown notes with version history, wiki links, tags, attachments, saved views, and a trash lifecycle.

Source: `packages/notes/src/notes/` — port 8020, enabled by default, store `data/runtime/notes/` (`notes.db`, `assets.db`).

## Capabilities

Registration is split by concern (`capabilities/`: `batch`, `catalog`, `history`, `lifecycle`, `transfer`, `view`; shared runtime in `runtime.py`), all merged into `Registry("notes")` — 26 capabilities: `create_note`, `update_note`, `edit_note_range`, `delete_note`, `restore_note`, `purge_note`, `empty_trash`, `list_notes`, `get_note`, `get_note_toc`, `resolve_links`, `import_note`, `link_note`, `get_backlinks`, `list_tags`, `rename_tag`, `notes_stats`, `list_versions`, `read_version`, `restore_version`, `export_note`, `batch_notes`, `add_asset`, `get_notes_view`, `set_notes_view`, `mark_note_span`.

## Storage

`store.py` — `NoteStore` (SQLite `notes.db`):

- Version snapshots on every content change (`note_versions`, keeping the last `notes.history.per_note` versions, default 20).
- `[[wiki links]]` resolved on write into `note_links` — exact id first, then case-insensitive title; dangling links are dropped. This powers `get_backlinks`.
- Trash via `trashed_ts`; `purge_note`/`empty_trash` remove rows permanently.
- Escaped-LIKE full-text search over title/content; PRAGMA-based column migration.
- Link helpers in `store_links.py`; TOC, span marks, validation, and saved views in `toc.py`/`marks.py`/`validate.py`/`view.py`.

`assets.py` — `AssetStore`: metadata in SQLite `assets.db`, binaries under the workspace; size cap `notes.assets.max_mb` (default 20). A read-only assets router is mounted as `Wiring.extra_router` (`/api/notes/assets/...`).

## Background work

`wiring.py` starts `TrashPruner`: purge at startup and every 24 h according to `notes.trash.retention_days` (0 = no-op).

## Events

Publishes `note.created`, `note.edited`, `note.deleted`, `note.restored`, `note.purged`, and `notes.ui.changed`.

## Settings

`notes.history.per_note`, `notes.trash.retention_days`, `notes.assets.max_mb`, `notes.editor.autosave_s`, `notes.export.dir`, `notes.list.page_size`, `notes.sort.default`, plus UI-state keys (`notes.ui.*`) persisted for the frontend.
