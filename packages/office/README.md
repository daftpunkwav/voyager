# office

## Purpose

Office domain: create/read/update documents (doc) and decks (slides) as structured artifacts.

## Configuration

office.* settings keys (artifact workspace layout).

## Extension Points

New document family = one module under modules/ with capabilities.

## Model Experience

Tools (when the domain is enabled): office__create_doc / update_doc / ... Long-form editing is block-based; artifacts land under the workspace.

## Known Limitations

Default-off; no WYSIWYG frontend (chat artifact cards only).

## Deferred Work

Rendering fidelity; spreadsheets.
