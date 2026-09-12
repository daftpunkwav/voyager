"""Note history and content utilities: versions, outline, link resolution,
range edits, highlights.

Responsibilities:
- list_versions / read_version / restore_version: version history
  (restore snapshots the current content once)
- get_note_toc: heading outline for the outline panel
- resolve_links: [[wiki links]] to {raw, target_id, title} details
- edit_note_range: bounded in-place content edits
- mark_note_span: highlight marks over the note body
"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .marks import MarkError, apply_note_mark
from .runtime import DOMAIN, emit, get_any, registry, require_alive, require_deps
from .toc import extract_toc
from .validate import validate_content


@capability(registry, name="list_versions", description="Note version history list (newest first)")
def list_versions(note_id: str) -> dict:
    require_alive(note_id)
    versions = require_deps().store.list_versions(note_id)
    return {
        "note_id": note_id,
        "versions": versions,
        "current_chars": len((require_deps().store.get(note_id) or {}).get("content") or ""),
    }


@capability(
    registry, name="read_version", description="Read the content of a specific historical version"
)
def read_version(note_id: str, version: int) -> dict:
    dep = require_deps()
    require_alive(note_id)
    snap = dep.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.NOT_FOUND,
            f"Version not found: v{version}",
            hint="Use list_versions to see available versions",
        )
    return {"note_id": note_id, "version": version, **snap}


@capability(
    registry,
    name="restore_version",
    description="Restore a historical version's content as the current content (this itself snapshots once)",
    cost=2,
)
async def restore_version(note_id: str, version: int) -> dict:
    deps = require_deps()
    require_alive(note_id)
    snap = deps.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"Version not found: v{version}")
    deps.store.update(note_id, content=snap["content"])
    deps.store.sync_links(note_id, snap["content"])
    await emit("note.edited", note_id, restored_version=int(version))
    return get_any(note_id)


@capability(
    registry,
    name="get_note_toc",
    description="Note heading outline (level/text/line) for the outline panel and scroll positioning",
)
def get_note_toc(note_id: str) -> dict:
    note = require_alive(note_id)
    return {"note_id": note_id, "toc": extract_toc(note["content"])}


@capability(
    registry,
    name="resolve_links",
    description="Resolve [[wiki links]] in content into {raw,target_id,title} details; dangling links have an empty target_id",
)
def resolve_links(note_id: str) -> dict:
    note = require_alive(note_id)
    links = require_deps().store.resolve_link_targets(note["content"])
    return {
        "note_id": note_id,
        "links": links,
        "resolved": sum(1 for i in links if i["target_id"]),
        "unresolved": sum(1 for i in links if not i["target_id"]),
    }


@capability(
    registry,
    name="edit_note_range",
    description="Atomically replace a content range by character offsets ([start,end); backs the frontend selection toolbar for bold/italic/highlight)",
    cost=2,
)
async def edit_note_range(note_id: str, start: int, end: int, new_text: str) -> dict:
    deps = require_deps()
    note = require_alive(note_id)
    content = note["content"]
    if not (0 <= start <= end <= len(content)):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"Range [{start},{end}) is outside the content (length {len(content)})",
        )
    new_content = content[:start] + (new_text or "") + content[end:]
    deps.store.update(note_id, content=new_content)
    deps.store.sync_links(note_id, new_content)
    await emit("note.edited", note_id, range_edit=True, start=start, end=end)
    return get_any(note_id)


@capability(
    registry,
    name="mark_note_span",
    description="Add or remove a highlight on the first visible occurrence in the content, outside code fences."
    "tone=warm|cool|rose|lime|violet|sand colors;"
    " rgbRRGGBB / #RRGGBB / RRGGBB give a custom color; clear removes it."
    " Syntax ==tone:text== (still Markdown). Nothing inside code fences or inline code is colored;"
    " ASCII box-drawing/table rows are skipped as whole lines. An existing highlight wrapped by a larger selection is flattened first, never nested."
    " The user toolbar and this capability are equivalent.",
    cost=2,
)
async def mark_note_span(note_id: str, quote: str, tone: str = "warm") -> dict:
    deps = require_deps()
    note = require_alive(note_id)
    try:
        new_content = apply_note_mark(note["content"], quote, tone)
    except MarkError as exc:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, str(exc)) from exc
    if new_content == note["content"]:
        return note
    validate_content(new_content)
    deps.store.update(note_id, content=new_content)
    deps.store.sync_links(note_id, new_content)
    await emit("note.edited", note_id, mark_span=True, tone=tone)
    return get_any(note_id)
