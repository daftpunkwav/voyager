"""Note import/export: Markdown read/write confined to the workspace
jail (light front-matter).

Responsibilities:
- export_markdown / export_note: serialize a note to Markdown with a light
  YAML front-matter (title and tags)
- import_note: read a Markdown file back into a note (size-capped)
- split_front_matter: parse the leading '---' block, body kept verbatim
- workspace_root: the jail root; fails closed when not injected
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from platform_capability import capability
from platform_contracts import DomainEvent, ErrorSuffix, ServiceError

from .runtime import DOMAIN, emit, get_any, registry, require_alive, require_deps
from .validate import MAX_IMPORT_BYTES, validate_content, validate_tag, validate_title

UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def workspace_root() -> Path:
    """Workspace jail root. Fails closed when not injected, so a misconfigured
    fixture can never open arbitrary-path access.
    """
    root = require_deps().workspace
    if root is None:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.UNAVAILABLE,
            "Workspace is not configured; path-based reads and writes are refused",
            hint="Both standalone and aggregate runs must inject it via wiring.wire(workspace=...)",
        )
    return Path(root)


def split_front_matter(text: str) -> tuple[str, list[str], str]:
    """Parse lightweight YAML front-matter: title and tags ([a,b] or one "- a" per line).

    Only a leading '---' block is recognized; all other fields are ignored
    and the body after the block is kept verbatim.
    """
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", [], text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return "", [], text
    title = ""
    tags: list[str] = []
    in_tags_list = False
    for line in lines[1:end]:
        stripped = line.strip()
        if stripped.startswith("- ") and in_tags_list:
            tags.append(stripped[2:].strip().strip("'\""))
            continue
        in_tags_list = False
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "title":
            title = value.strip("'\"")
        elif key == "tags":
            in_tags_list = True
            if value.startswith("[") and value.endswith("]"):
                tags = [t.strip().strip("'\"") for t in value[1:-1].split(",") if t.strip()]
                in_tags_list = False
            elif not value:
                continue
    body = "\n".join(lines[end + 1 :])
    return title, [t for t in tags if t], body


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def export_markdown(note: dict) -> dict:
    deps = require_deps()
    root = workspace_root()
    export_dir_setting = ""
    if deps.settings is not None:
        export_dir_setting = str(deps.settings.get("notes.export.dir") or "")
    raw = export_dir_setting or "workspace/notes-export"
    export_dir = Path(raw)
    if not export_dir.is_absolute():
        export_dir = root / export_dir
    export_dir = export_dir.resolve()
    if not _within(export_dir, root):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "Export directory must be inside the workspace",
            hint="notes.export.dir must not point outside the jail",
        )
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_title = UNSAFE_FILENAME_RE.sub("_", note["title"]).strip(" .")[:80] or "untitled"
    dest = export_dir / f"{safe_title}_{note['id']}.md"
    body = (
        "---\n"
        f"id: {note['id']}\n"
        f"title: {note['title']}\n"
        f"tags: {json.dumps(note['tags'], ensure_ascii=False)}\n"
        f"created: {_fmt_ts(note['created_ts'])}\n"
        f"updated: {_fmt_ts(note['updated_ts'])}\n"
        "---\n\n" + note["content"]
    )
    dest.write_text(body, encoding="utf-8")
    return {"note_id": note["id"], "path": str(dest), "chars": len(body)}


@capability(
    registry,
    name="import_note",
    description="Import an external .md file (YAML front-matter title/tags optionally applied)",
    cost=2,
)
async def import_note(file_path: str, title: str = "", tags: list[str] | None = None) -> dict:
    deps = require_deps()
    root = workspace_root()
    src = Path(file_path)
    if not _within(src, root):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "File must live under workspace/",
            hint="Place the .md under workspace/ first, then import; reading outside the jail is forbidden",
        )
    if not src.is_file():
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"File not found: {file_path}")
    if src.stat().st_size > MAX_IMPORT_BYTES:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"File exceeds the import limit of {MAX_IMPORT_BYTES} bytes",
        )
    raw = await asyncio.to_thread(src.read_text, encoding="utf-8", errors="replace")
    meta_title, meta_tags, body = split_front_matter(raw)
    validate_content(body)
    clean_tags = [validate_tag(t) for t in (tags or [])] or [validate_tag(t) for t in meta_tags]
    final_title = validate_title(title or meta_title or src.stem)
    nid = deps.store.create({"title": final_title, "content": body, "tags": clean_tags})
    deps.store.sync_links(nid, body)
    await emit(DomainEvent.NOTE_CREATED, nid, title=final_title, imported=True)
    return get_any(nid)


@capability(
    registry,
    name="export_note",
    description="Export as a Markdown file (front-matter + body), returning the written path",
    cost=1,
)
async def export_note(note_id: str) -> dict:
    return export_markdown(require_alive(note_id))
