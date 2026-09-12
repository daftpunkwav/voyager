# notes

## Purpose

Notes domain: markdown notes with versions, links, tags, trash, attachments, and view/batch operations.

## Configuration

notes.* settings keys (see settings.py): page size, editor behavior defaults.

## Extension Points

Add a capability by registering into `capabilities.py`'s registry (REST + agent bridge automatic); persistence lives in store/store_links.

## Model Experience

Tools: notes__create_note, notes__list_notes, notes__update_note, notes__link_note, ... Titles/content in plain text; results return note ids. Use for anything the user wants persisted as a document.

## Known Limitations

Full-text search relies on the sources domain, not here; attachment previews are minimal.

## Deferred Work

Granular per-note ACLs; richer markdown extensions.
