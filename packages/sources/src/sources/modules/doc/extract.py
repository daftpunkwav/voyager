"""Document text extractors: pure functions dispatched by extension; the
worker only handles scheduling and events.

Responsibilities:
- extract_sections: dispatch by extension into a Section list
- Per-format extractors: pdf (outline cues from bookmarks), epub (spine
  order), docx, and plain text/markdown

Design constraints:
- Extraction failure raises ExtractError with a user-readable reason; it
  never silently returns empty.
- Unknown extensions never reach this module; the capabilities layer
  marks them 'stored' (archive semantics) directly.
- Section splitting relies only on the text itself: structural cues
  (bookmarks/heading styles) when present, length-based otherwise.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

#: Soft per-chapter cap (chars); unstructured docs chunk at this size,
#: oversized chunks split further on blank lines
_CHAPTER_TARGET = 8000

#: EPUB decompression caps: the import pipeline limits the compressed file
#: size, not what the zip expands to — a zip bomb must not exhaust memory.
#: Per-spine-entry cap plus a total budget across all entries (the OPF and
#: each spine file count against it).
_MAX_EPUB_ENTRY_BYTES = 20 * 1024 * 1024
_MAX_EPUB_TOTAL_BYTES = 200 * 1024 * 1024


class ExtractError(Exception):
    """Extraction failure (encrypted/corrupt/empty); the worker catches it
    and marks the document failed.
    """


@dataclass
class Section:
    section_no: int
    title: str
    page_start: int
    page_end: int
    text: str


def extract_sections(path: str | Path, ext: str) -> list[Section]:
    ext = ext.lower()
    if ext == ".pdf":
        return _from_pdf(Path(path))
    if ext == ".epub":
        return _from_epub(Path(path))
    if ext == ".docx":
        return _from_docx(Path(path))
    if ext in (".txt", ".md", ".markdown"):
        return _from_text(Path(path))
    raise ExtractError(f"Unsupported parse format: {ext}")


# ---------- PDF ----------


def _from_pdf(path: Path) -> list[Section]:
    import pypdfium2 as pdfium  # lazy import: non-PDF paths skip the load cost

    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as exc:  # corrupt/encrypted uniformly becomes a user-readable error
        raise ExtractError(f"Failed to open PDF: {exc}") from exc
    try:
        if doc.is_encrypted:
            raise ExtractError("PDF is encrypted; parsing is not supported yet")
        page_texts: list[str] = []
        for page in doc:
            textpage = page.get_textpage()
            page_texts.append(textpage.get_text_bounded() or "")
            textpage.close()
            page.close()
        outline = _pdf_outline(doc)
        sections: list[Section] = []
        if outline:
            # Bookmark chapters: pages between adjacent bookmarks form one chapter
            marks = sorted((page_no, title) for page_no, title in outline)
            for i, (page_no, title) in enumerate(marks):
                end = marks[i + 1][0] if i + 1 < len(marks) else len(page_texts)
                text = "\n".join(page_texts[page_no:end]).strip()
                if text:
                    sections.append(Section(len(sections) + 1, title, page_no + 1, end, text))
        if not sections:
            # No bookmarks: one chapter per 10 pages
            for start in range(0, len(page_texts), 10):
                text = "\n".join(page_texts[start : start + 10]).strip()
                if text:
                    sections.append(
                        Section(
                            len(sections) + 1, "", start + 1, min(start + 10, len(page_texts)), text
                        )
                    )
        if not sections:
            raise ExtractError(
                "PDF has no extractable text (possibly a scanned document; OCR is not supported yet)"
            )
        return sections
    finally:
        doc.close()


def _pdf_outline(doc) -> list[tuple[int, str]]:
    """Bookmarks -> (0-based page number, title); bookmarks with out-of-range
    pages are dropped.
    """
    try:
        raw = doc.get_toc()
    except Exception:  # noqa: BLE001  # outline parse failure treated as no bookmarks
        return []
    marks: list[tuple[int, str]] = []
    count = len(doc)
    for item in raw:
        idx = item.page_index
        if idx is not None and 0 <= idx < count:
            marks.append((idx, item.title or ""))
    return marks


# ---------- EPUB ----------

_XHTML_NS = "{http://www.w3.org/1999/xhtml}"
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}


def _read_entry(zf: zipfile.ZipFile, name: str, budget: list[int]) -> bytes:
    """Read one zip entry under the per-entry cap and the shared total budget;
    raises ExtractError so a zip bomb fails the import instead of the process."""
    info = zf.getinfo(name)
    if info.file_size > _MAX_EPUB_ENTRY_BYTES:
        raise ExtractError(
            f"EPUB entry exceeds the {_MAX_EPUB_ENTRY_BYTES // (1024 * 1024)}MB limit: {name}"
        )
    if info.file_size > budget[0]:
        raise ExtractError("EPUB expands beyond the decompression budget")
    budget[0] -= info.file_size
    return zf.read(name)


def _from_epub(path: Path) -> list[Section]:
    try:
        zf = zipfile.ZipFile(path)
    except Exception as exc:
        raise ExtractError(f"Failed to open EPUB: {exc}") from exc
    with zf:
        budget = [_MAX_EPUB_TOTAL_BYTES]
        spine_files = _epub_spine(zf, budget)
        sections: list[Section] = []
        for i, name in enumerate(spine_files):
            try:
                root = ElementTree.fromstring(_read_entry(zf, name, budget))
            except ElementTree.ParseError:
                continue
            title = _first_heading(root)
            text = _strip_xhtml(root)
            if not text.strip():
                continue
            sections.append(Section(len(sections) + 1, title, i + 1, i + 1, text))
        if not sections:
            raise ExtractError("EPUB has no extractable text")
        return sections


def _epub_spine(zf: zipfile.ZipFile, budget: list[int]) -> list[str]:
    """XHTML file paths in OPF spine order; falls back to all .x?html files
    when the OPF cannot be parsed.
    """
    names = zf.namelist()
    opf_name = next((n for n in names if n.endswith(".opf")), None)
    if opf_name is None:
        return [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]
    base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
    try:
        root = ElementTree.fromstring(_read_entry(zf, opf_name, budget))
    except ElementTree.ParseError:
        return [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]
    manifest: dict[str, str] = {}
    for item in root.iter():
        if item.tag.endswith("}item") or item.tag == "item":
            iid, href = item.get("id"), item.get("href")
            if iid and href:
                manifest[iid] = href
    order: list[str] = []
    for item in root.iter():
        if item.tag.endswith("}itemref") or item.tag == "itemref":
            idref = item.get("idref")
            href = manifest.get(idref or "")
            if href:
                full = (base + href).lstrip("/")
                if full in names:
                    order.append(full)
    return order


def _first_heading(root: ElementTree.Element) -> str:
    for el in root.iter():
        if el.tag in {f"{_XHTML_NS}h{i}" for i in range(1, 7)} | {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            return (el.text or "").strip()[:100]
    return ""


def _strip_xhtml(root: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(el) -> None:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("script", "style"):
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in _BLOCK_TAGS:
            parts.append("\n")

    walk(root)
    return re.sub(r"[ \t]+", " ", "".join(parts)).strip()


# ---------- DOCX ----------


def _from_docx(path: Path) -> list[Section]:
    import docx  # lazy import

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ExtractError(f"Failed to open DOCX: {exc}") from exc
    sections: list[Section] = []
    buf: list[str] = []
    title = ""

    def flush() -> None:
        nonlocal buf
        text = "\n".join(buf).strip()
        if text:
            sections.append(Section(len(sections) + 1, title, 0, 0, text))
        buf = []

    for para in document.paragraphs:
        style = (para.style.name or "") if para.style is not None else ""
        style_id = (para.style.style_id or "") if para.style is not None else ""
        if style.startswith("Heading") or style_id.lower().startswith("heading"):
            flush()
            title = para.text.strip()[:100]
            buf = [para.text]
        else:
            buf.append(para.text)
        if sum(len(b) for b in buf) > _CHAPTER_TARGET and title:
            flush()
            title = ""
    flush()
    if not sections:
        raise ExtractError("DOCX has no extractable text")
    return sections


# ---------- Plain text ----------


def _from_text(path: Path) -> list[Section]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ExtractError(f"Failed to read file: {exc}") from exc
    if not text.strip():
        raise ExtractError("File is empty")
    if len(text) <= _CHAPTER_TARGET:
        return [Section(1, "", 0, 0, text)]
    # Split on blank lines and accumulate chunks up to the target chapter
    # size (for md, a heading line can serve as the chapter title)
    chunks = re.split(r"\n\s*\n", text)
    sections: list[Section] = []
    buf: list[str] = []
    size = 0
    for chunk in chunks:
        buf.append(chunk)
        size += len(chunk)
        if size >= _CHAPTER_TARGET:
            joined = "\n\n".join(buf).strip()
            sections.append(Section(len(sections) + 1, _md_title(joined), 0, 0, joined))
            buf, size = [], 0
    if buf:
        joined = "\n\n".join(buf).strip()
        if joined:
            sections.append(Section(len(sections) + 1, _md_title(joined), 0, 0, joined))
    return sections


def _md_title(text: str) -> str:
    """The leading ATX heading line of a chunk becomes the chapter title
    (md/txt heuristic; empty when absent).
    """
    first = text.split("\n", 1)[0].strip()
    if first.startswith("#"):
        return first.lstrip("#").strip()[:100]
    return ""
