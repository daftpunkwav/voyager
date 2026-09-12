"""Note lifecycle: create/read/update/link/trash-restore-purge.

Responsibilities:
- create_note / get_note / list_notes: create, full-text fetch, and
  filtered/sorted listing (state=active/archived/trash/all)
- update_note: title/content/tags/pinned/archived writes; content changes
  snapshot a version automatically
- link_note: attach a note to a source or graph node (empty string clears)
- delete_note / restore_note / purge_note / empty_trash: the trash flow,
  including asset purge on permanent deletion
"""

from __future__ import annotations

import time

from platform_capability import capability
from platform_contracts import DomainEvent, ErrorSuffix, ServiceError

from .runtime import DOMAIN, SORT_COL, STATES, emit, get_any, registry, require_alive, require_deps
from .validate import (
    validate_content,
    validate_node_id,
    validate_source_id,
    validate_tag,
    validate_title,
)


@capability(registry, name="create_note", description="Create a Markdown note", cost=2)
async def create_note(
    title: str,
    content: str = "",
    tags: list[str] | None = None,
    source_id: str = "",
    node_id: str = "",
) -> dict:
    deps = require_deps()
    title = validate_title(title)
    validate_content(content)
    clean_tags = [validate_tag(t) for t in (tags or [])]
    source_id = validate_source_id(source_id)
    node_id = validate_node_id(node_id)
    nid = deps.store.create(
        {
            "title": title,
            "content": content,
            "tags": clean_tags,
            "source_id": source_id,
            "node_id": node_id,
        }
    )
    deps.store.sync_links(nid, content)
    await emit(DomainEvent.NOTE_CREATED, nid, title=title)
    return get_any(nid)


@capability(
    registry,
    name="get_note",
    description="Fetch a note's full text on demand (also readable inside the trash)",
)
def get_note(note_id: str) -> dict:
    return get_any(note_id)


@capability(
    registry,
    name="list_notes",
    description="Note summary list (state=active/archived/trash/all;"
    " query searches titles and content; sort=updated/created/title)",
)
def list_notes(
    source_id: str | None = None,
    tag: str = "",
    query: str = "",
    state: str = "active",
    sort: str = "",
    limit: int = 100,
) -> list[dict]:
    """sort falls back to the notes.sort.default setting; invalid state falls back to active."""
    deps = require_deps()
    key = sort or (deps.settings.get("notes.sort.default") if deps.settings else "")
    order = SORT_COL.get(key, "updated_ts")
    view = state if state in STATES else "active"
    limit = max(1, min(int(limit), 500))
    page_size_cap = int(deps.settings.get("notes.list.page_size") or 0) if deps.settings else 0
    if page_size_cap and limit > page_size_cap:
        limit = page_size_cap
    return deps.store.list(
        source_id=source_id, tag=tag, query=query, state=view, sort=order, limit=limit
    )


@capability(
    registry,
    name="update_note",
    description="Update a note's title/content/tags/pinned/archived state (content changes snapshot a version automatically)",
    cost=2,
)
async def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> dict:
    deps = require_deps()
    require_alive(note_id)
    if title is not None:
        title = validate_title(title)
    validate_content(content)
    clean_tags = [validate_tag(t) for t in tags] if tags is not None else None
    deps.store.history_keep = (
        int(deps.settings.get("notes.history.per_note") or 0)
        if deps.settings
        else deps.store.history_keep
    )
    changed = deps.store.update(
        note_id,
        title=title,
        content=content,
        tags=clean_tags,
        pinned=pinned,
        archived=archived,
    )
    if not changed:
        return get_any(note_id)
    if content is not None:
        deps.store.sync_links(note_id, content)
    await emit(
        "note.edited",
        note_id,
        content_changed=content is not None,
        pinned=pinned,
        archived=archived,
    )
    return get_any(note_id)


@capability(
    registry,
    name="link_note",
    description="Link a note to a source or graph node (pass an empty string to clear)",
    cost=2,
)
async def link_note(note_id: str, source_id: str | None = None, node_id: str | None = None) -> dict:
    """None leaves the link untouched; an empty string clears it.

    Both agents and users may maintain the note's references.
    """
    deps = require_deps()
    require_alive(note_id)
    if source_id is not None:
        source_id = validate_source_id(source_id)
    if node_id is not None:
        node_id = validate_node_id(node_id)
    deps.store.update(note_id, source_id=source_id, node_id=node_id)
    await emit("note.edited", note_id, linked=True)
    return get_any(note_id)


@capability(
    registry,
    name="delete_note",
    description="Move a note to the trash (recoverable)",
    reversible=True,
)
async def delete_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    if note["trashed_ts"] is not None:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.CONFLICT,
            "Note is already in the trash",
            hint="restore_note can recover it",
        )
    deps.store.trash(note_id)
    await emit("note.deleted", note_id, title=note["title"])
    return {
        "trashed": note_id,
        "title": note["title"],
        "hint": "restore_note recovers it; purge_note deletes it permanently",
    }


@capability(registry, name="restore_note", description="Restore a note from the trash")
async def restore_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    if note["trashed_ts"] is None:
        raise ServiceError(DOMAIN, ErrorSuffix.CONFLICT, "Note is not in the trash")
    deps.store.restore(note_id)
    await emit("note.restored", note_id, title=note["title"])
    return get_any(note_id)


@capability(
    registry,
    name="purge_note",
    description="Permanently delete a note with its versions and links (irreversible)",
    reversible=False,
)
async def purge_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    deps.store.delete(note_id)
    removed_assets = deps.purge_assets(note_id) if deps.purge_assets else []
    await emit("note.purged", note_id, title=note["title"], removed_assets=len(removed_assets))
    return {"purged": note_id, "title": note["title"]}


@capability(
    registry,
    name="empty_trash",
    description="Empty the trash (bulk purge is refused when notes.trash.retention_days is 0)",
    reversible=False,
)
async def empty_trash(max_age_days: int | None = None) -> dict:
    """No argument purges the whole trash; with N, only notes trashed more than N days ago."""
    deps = require_deps()
    rows = deps.store.list(state="trash", limit=10000)
    cutoff = None
    if max_age_days is not None:
        cutoff = time.time() - max_age_days * 86400
    purged: list[str] = []
    for row in rows:
        trashed_ts = row.get("trashed_ts")
        if cutoff is not None and (trashed_ts is None or trashed_ts > cutoff):
            continue
        purged.append(row["id"])
    if not purged:
        return {"purged_count": 0}
    deps.store.delete_many(purged)
    if deps.purge_assets:
        for nid in purged:
            deps.purge_assets(nid)
    await emit("note.purged_batch", purged[0], purged_count=len(purged), note_ids=purged)
    return {"purged_count": len(purged)}
