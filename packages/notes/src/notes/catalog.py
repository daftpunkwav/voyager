"""Note catalog capabilities: tags, backlinks, and counts.

Responsibilities:
- list_tags / rename_tag: tag listing with counts and global rename
- get_backlinks: which live notes link to a given note
- notes_stats: count statistics (active/archived/trash/top tags)
"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .runtime import DOMAIN, get_any, registry, require_deps
from .validate import validate_tag


@capability(registry, name="list_tags", description="Tag list of live notes (with counts)")
def list_tags() -> list[dict]:
    return [{"tag": t, "count": c} for t, c in require_deps().store.all_tags()]


@capability(
    registry, name="rename_tag", description="Rename a tag globally (applies to all notes)", cost=2
)
async def rename_tag(old: str, new: str) -> dict:
    old = validate_tag(old)
    new = validate_tag(new)
    if old == new:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "Old and new tags are identical")
    count = require_deps().store.rename_tag(old, new)
    return {"renamed_from": old, "to": new, "affected": count}


@capability(
    registry, name="get_backlinks", description="Backlinks: which live notes link to this note"
)
def get_backlinks(note_id: str) -> dict:
    get_any(note_id)
    links = require_deps().store.backlinks(note_id)
    return {"note_id": note_id, "backlinks": links}


@capability(
    registry, name="notes_stats", description="Count statistics (active/archived/trash/top tags)"
)
def notes_stats() -> dict:
    return require_deps().store.stats()
