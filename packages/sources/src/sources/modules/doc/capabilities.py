"""Doc submodule capabilities: import / list / outline / section read /
search / metadata / removal.

Import is a long-running task: register -> enqueue parse -> emit
source.ready on completion. Unknown extensions are accepted with archive
semantics (status 'stored') -- the library takes anything and parsing
support grows incrementally.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    JobRef,
    ServiceError,
)
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .._shared.events import with_session
from .._shared.text import valid_tag
from .store import DocStore

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

#: Parseable formats (extract.py dispatches on these); others use archive semantics
PARSEABLE_EXTS = (".pdf", ".epub", ".docx", ".txt", ".md", ".markdown")

_DOC_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.doc")

_DEFAULT_MAX_FILE_MB = 200

# Filename sanitization shared with the legacy books import: stops a
# title/filename from escaping the doc directory
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME_RE.sub("_", name).strip(" .")[:120]
    if not cleaned:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "Filename is empty after sanitization: cannot consist only of path separators/reserved characters",
        )
    if Path(cleaned).stem.upper() in _RESERVED_NAMES:
        cleaned = f"doc_{cleaned}"
    return cleaned


@dataclass
class DocDeps:
    store: DocStore
    bus: EventBus | None
    queue: asyncio.Queue  # parse jobs: doc_id
    workspace: Path  # storage root (workspace/doc/)
    settings: SettingsStore | None = None  # read for sources.doc.max_file_mb

    def max_file_mb(self) -> int:
        raw = self.settings.get("sources.doc.max_file_mb") if self.settings else None
        return int(raw or _DEFAULT_MAX_FILE_MB)


_deps: DocDeps | None = None


def init_deps(deps: DocDeps) -> None:
    global _deps
    _deps = deps


def require_deps() -> DocDeps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at the service entry point first")
    return _deps


def _require_doc(did: str) -> dict:
    doc = require_deps().store.get(did)
    if doc is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Document not found: {did}")
    return doc


def _validate_input(
    file_path: str, title: str, tags: list[str], max_file_mb: int
) -> tuple[Path, str, str]:
    """Returns (source path, extension, title); raises INVALID_INPUT on failure."""
    src = Path(file_path)
    if not src.is_file():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"File not found: {file_path}")
    if max_file_mb > 0 and src.stat().st_size > max_file_mb * 1024 * 1024:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"File exceeds the size limit of {max_file_mb}MB",
            hint="Adjust via the sources.doc.max_file_mb setting",
        )
    for tag in tags:
        if not valid_tag(tag):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"Invalid tag: {tag} (max 32 chars; forbidden \\\"\\',[] characters)",
            )
    ext = src.suffix.lower()
    clean_title = title.strip() or src.stem.strip() or "Untitled document"
    return src, ext, clean_title[:200]


@capability(
    registry,
    name="add_document",
    description="Import a document into the library and parse it in the background (PDF/EPUB/DOCX/TXT/MD get section extraction;"
    " other formats are archived only). file_path must be a server-reachable path"
    " (browser uploads land in workspace/imports/ via /api/uploads, then pass the path).",
    long_running=True,
    cost=2,
)
async def add_document(
    file_path: str,
    title: str = "",
    tags: list[str] | None = None,
    category: str = "",
    _actor: ActorRef | None = None,
) -> JobRef:
    deps = require_deps()
    # Jail check before stat: avoids leaking outside-jail paths via
    # "file not found"
    if not _within(Path(file_path), deps.workspace):
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "File must live under workspace/ (uploaded via /api/uploads)",
            hint="Agents may download/copy the file into workspace/ first, then import",
        )
    src, ext, clean_title = _validate_input(file_path, title, list(tags or []), deps.max_file_mb())
    dest_dir = Path(deps.workspace) / "doc"
    dest_dir.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    dest = dest_dir / f"{_safe_filename(clean_title)}_{uid}{ext}"
    await asyncio.to_thread(shutil.copy2, src, dest)
    status = "parsing" if ext in PARSEABLE_EXTS else "stored"
    did = deps.store.add(
        {
            "title": clean_title,
            "filename": src.name,
            "ext": ext,
            "local_path": str(dest),
            "category": category,
            "tags": list(tags or []),
            "status": status,
        }
    )
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_ADDED,
                actor=_DOC_ACTOR,
                payload=with_session({"source_id": did, "kind": "doc", "title": clean_title}),
            )
        )
    if status == "parsing":
        deps.queue.put_nowait(did)
    return JobRef(job_id=did)


@capability(
    registry,
    name="list_documents",
    description="Document list (summaries, no section bodies)",
    write=False,
)
def list_documents(
    status: str = "",
    tag: str = "",
    query: str = "",
    sort: str = "added",
    desc: bool = True,
    limit: int = 200,
) -> list[dict]:
    return require_deps().store.list(
        status=status, tag=tag, query=query, sort=sort, desc=desc, limit=min(limit, 500)
    )


@capability(
    registry,
    name="get_document",
    description="Single document detail (section outline included, no body)",
    write=False,
)
def get_document(doc_id: str) -> dict:
    doc = _require_doc(doc_id)
    doc["sections"] = require_deps().store.sections_outline(doc_id)
    doc["total_sections"] = len(doc["sections"])
    return doc


@capability(
    registry,
    name="get_doc_section",
    description="Fetch a document section's full text on demand (1-based section number)",
    write=False,
)
def get_doc_section(doc_id: str, section_no: int = 1) -> dict:
    deps = require_deps()
    _require_doc(doc_id)
    section = deps.store.section(doc_id, section_no)
    if section is None:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.NOT_FOUND,
            f"Section not found: {section_no}",
            hint="Use get_document to see the outline first",
        )
    section["doc_id"] = doc_id
    section["total_sections"] = deps.store.sections_count(doc_id)
    return section


@capability(
    registry,
    name="search_documents",
    description="Document full-text search: hits return section number and snippet",
    write=False,
)
def search_documents(query: str, limit: int = 20) -> list[dict]:
    if not query.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "query cannot be empty")
    return require_deps().store.search_sections(query.strip(), min(limit, 50))


@capability(
    registry,
    name="set_document_meta",
    description="Set document category/tags/progress/note/title (aligned with set_repo_meta)",
)
def set_document_meta(
    doc_id: str,
    title: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    progress: str | None = None,
    note: str | None = None,
) -> dict:
    deps = require_deps()
    _require_doc(doc_id)
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid tag: {tag}")
    deps.store.set_meta(
        doc_id, title=title, category=category, tags=tags, progress=progress, note=note
    )
    return _require_doc(doc_id)


@capability(
    registry,
    name="remove_document",
    description="Delete a document's record/sections and local copy",
    reversible=False,
    cost=2,
)
async def remove_document(doc_id: str) -> dict:
    deps = require_deps()
    doc = _require_doc(doc_id)
    deps.store.remove(doc_id)
    if doc["local_path"] and _within(Path(doc["local_path"]), deps.workspace):
        # Local file cleanup is done asynchronously by the worker
        # (same queue as parsing, order preserved)
        deps.queue.put_nowait(("remove", doc_id, doc["local_path"]))
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_REMOVED,
                actor=_DOC_ACTOR,
                payload=with_session({"source_id": doc_id, "kind": "doc", "title": doc["title"]}),
            )
        )
    return {"removed": doc_id, "title": doc["title"]}


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False
