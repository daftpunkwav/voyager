"""EPUB parsing hardening: entity declarations and external entities in
spine entries or the OPF are rejected by defusedxml and must degrade to the
documented behavior (skip the section / fall back to the file list), never
crash the extractor or resolve external references.
"""

import zipfile

from sources.modules.doc.extract import extract_sections


def _write_epub(path, opf: str, chapters: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        for name, body in chapters.items():
            zf.writestr(name, body)
        zf.writestr("content/book.opf", opf)


def test_epub_entity_expansion_in_spine_entry_is_skipped(tmp_path) -> None:
    # Internal entity amplification (billion-laughs style): the entry must be
    # skipped, not expanded, and the healthy chapter must still extract.
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE html ['
        '<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        "]><html><body><h1>Bomb</h1><p>&b;</p></body></html>"
    )
    p = tmp_path / "b.epub"
    _write_epub(
        p,
        "<package><manifest>"
        '<item id="c1" href="ch1.xhtml"/>'
        '<item id="c2" href="ch2.xhtml"/>'
        "</manifest><spine>"
        '<itemref idref="c1"/><itemref idref="c2"/>'
        "</spine></package>",
        {"content/ch1.xhtml": bomb, "content/ch2.xhtml": "<html><body><h1>Two</h1></body></html>"},
    )
    sections = extract_sections(p, ".epub")
    assert [s.title for s in sections] == ["Two"]


def test_epub_external_entity_does_not_read_files(tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    xxe = (
        '<?xml version="1.0"?><!DOCTYPE html ['
        '<!ENTITY xxe SYSTEM "file:///' + str(secret).replace("\\", "/") + '">'
        "]><html><body><h1>Steal</h1><p>&xxe;</p></body></html>"
    )
    p = tmp_path / "b.epub"
    _write_epub(
        p,
        "<package><manifest>"
        '<item id="c1" href="ch1.xhtml"/>'
        '<item id="c2" href="ch2.xhtml"/>'
        "</manifest><spine>"
        '<itemref idref="c1"/><itemref idref="c2"/>'
        "</spine></package>",
        {"content/ch1.xhtml": xxe, "content/ch2.xhtml": "<html><body><h1>Two</h1></body></html>"},
    )
    sections = extract_sections(p, ".epub")
    assert [s.title for s in sections] == ["Two"]
    joined = "\n".join(s.text for s in sections)
    assert "TOPSECRET" not in joined


def test_epub_entity_in_opf_falls_back_to_file_list(tmp_path) -> None:
    # An OPF that defusedxml refuses to parse falls back to the plain
    # .x?html file list; extraction still succeeds.
    opf = (
        '<?xml version="1.0"?><!DOCTYPE package [<!ENTITY a "x">]'
        "<package><manifest>&a;"
        '<item id="c1" href="ch1.xhtml"/>'
        '</manifest><spine><itemref idref="c1"/></spine></package>'
    )
    p = tmp_path / "b.epub"
    _write_epub(
        p,
        opf,
        {
            "content/ch1.xhtml": "<html><body><h1>One</h1></body></html>",
            "content/ch2.xhtml": "<html><body><h1>Two</h1></body></html>",
        },
    )
    sections = extract_sections(p, ".epub")
    assert [s.title for s in sections] == ["One", "Two"]
