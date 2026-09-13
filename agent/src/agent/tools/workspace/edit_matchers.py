"""Fuzzy match chain for edit_file: locate a unique old_text span that the
exact match failed to find.

The chain mirrors the replacer ladder used by mainstream coding agents
(exact -> line-trimmed -> block anchor -> whitespace-normalized ->
escape-normalized): each level is tried in order and only a UNIQUE match is
accepted; a level finding several candidates records the ambiguity and the
chain keeps degrading. Everything here is pure text surgery - no I/O, no
policy - so edit_file stays the only writer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

#: Similarity floor for the middle lines of a block-anchor match
BLOCK_SIMILARITY = 0.65

#: A candidate window this many lines longer than old_text is disproportionate
BLOCK_MAX_EXTRA_LINES = 2

#: Character bloat guards for block anchors (mirrors disproportionate rules)
BLOCK_MAX_CHAR_RATIO = 4
BLOCK_MAX_EXTRA_CHARS = 500

_ESCAPE_MAP = {"\\n": "\n", "\\t": "\t", "\\r": "\r", '\\"': '"', "\\'": "'"}

Finder = Callable[[str, str], list[tuple[int, int]]]


@dataclass(frozen=True)
class MatchResult:
    """Outcome of the chain: a unique span, or why none was accepted."""

    span: tuple[int, int] | None
    level: str | None
    #: Candidate count of the least-degraded ambiguous level (0 = none)
    ambiguous: int
    #: Leading indentation of the first matched line, for whole-line matches
    #: where old_text itself is unindented (None otherwise)
    line_indent: str | None = None
    #: True when the span swallowed a line terminator old_text ended with
    consumed_eol: bool = False


@dataclass(frozen=True)
class _Line:
    """A physical line of the haystack with its offsets in the original text."""

    start: int
    #: Just past the last content char (newline terminator excluded)
    end: int
    #: Just past the newline terminator (== end for a final line without one)
    nl_end: int


def _line_table(text: str) -> list[_Line]:
    lines: list[_Line] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\n":
            end = i - 1 if i > start and text[i - 1] == "\r" else i
            lines.append(_Line(start, end, i + 1))
            start = i + 1
        i += 1
    if start < n or not lines:
        lines.append(_Line(start, n, n))
    return lines


def _split_core(old_text: str) -> tuple[list[str], bool, bool]:
    """Split into lines and report whether old_text starts/ends with a newline
    (the peeled "" before/after): a leading newline is the terminator of the
    line BEFORE the block, a trailing one the terminator of the last block
    line - so the span must consume them to cover exactly old_text's bytes."""
    lines = old_text.split("\n")
    lead = len(lines) > 1 and lines[0] == ""
    trail = len(lines) > 1 and lines[-1] == ""
    core = lines[1:-1] if lead and trail else lines[1:] if lead else lines[:-1] if trail else lines
    return core, lead, trail


def _full_line_matches(
    text: str,
    lines: list[_Line],
    old_text: str,
    line_eq: Callable[[str, _Line, str], bool],
) -> list[tuple[int, int]]:
    """Span finder shared by the full-line levels: match `core` against
    consecutive haystack lines with `line_eq`, consuming the newline before
    the block (leading "") and after the last block line (trailing "")."""
    core, lead, trail = _split_core(old_text)
    k = len(core)
    if k < 1 or k > len(lines):
        return []
    spans: list[tuple[int, int]] = []
    for i in range(len(lines) - k + 1):
        if not all(line_eq(text, lines[i + j], core[j]) for j in range(k)):
            continue
        if lead and i == 0:
            continue  # old's leading newline has no counterpart at file start
        start = lines[i - 1].end if lead else lines[i].start
        last = lines[i + k - 1]
        if trail:
            # consume the terminator; at EOF there may be none to consume
            end = max(last.end, last.nl_end)
        else:
            end = last.end
        spans.append((start, end))
    return spans


def _exact_spans(text: str, old_text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(re.escape(old_text), text)]


def _line_trimmed_spans(text: str, old_text: str) -> list[tuple[int, int]]:
    lines = _line_table(text)

    def eq(hay: str, line: _Line, needle: str) -> bool:
        return hay[line.start : line.end].strip() == needle.strip()

    return _full_line_matches(text, lines, old_text, eq)


def _block_anchor_spans(text: str, old_text: str) -> list[tuple[int, int]]:
    core, lead, trail = _split_core(old_text)
    k = len(core)
    if k < 3 or lead or trail:  # anchors need head+middle+tail inside old_text
        return []
    lines = _line_table(text)
    first, last = core[0].strip(), core[-1].strip()
    middle = "\n".join(line.strip() for line in core[1:-1])
    lo_len = max(3, -(-k * 3 // 4))  # ceil(0.75k): block may shrink up to 25%
    hi_len = max(lo_len, (k * 5) // 4)  # floor(1.25k): block may grow up to 25%
    spans: list[tuple[int, int]] = []
    for i in range(len(lines)):
        if text[lines[i].start : lines[i].end].strip() != first:
            continue
        for wlen in range(lo_len, hi_len + 1):
            j = i + wlen - 1
            if j >= len(lines):
                break
            if text[lines[j].start : lines[j].end].strip() != last:
                continue
            if wlen >= k + BLOCK_MAX_EXTRA_LINES:
                continue  # disproportionate: keep searching, never accept
            window = text[lines[i].start : lines[j].end]
            if len(window) > BLOCK_MAX_CHAR_RATIO * len(old_text) or (
                len(window) - len(old_text) > BLOCK_MAX_EXTRA_CHARS
            ):
                continue
            window_middle = "\n".join(
                text[lines[x].start : lines[x].end].strip() for x in range(i + 1, j)
            )
            if SequenceMatcher(None, middle, window_middle).ratio() < BLOCK_SIMILARITY:
                continue
            spans.append((lines[i].start, lines[j].end))
    return spans


def _ws_normalize(s: str) -> tuple[str, list[tuple[int, int]]]:
    """Collapse every whitespace run to one space, keeping a per-output-char
    map back to source spans so matches can be projected onto the original."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i].isspace():
            j = i
            while j < n and s[j].isspace():
                j += 1
            out.append(" ")
            spans.append((i, j))
            i = j
        else:
            out.append(s[i])
            spans.append((i, i + 1))
            i += 1
    return "".join(out), spans


def _whitespace_spans(text: str, old_text: str) -> list[tuple[int, int]]:
    norm_text, tmap = _ws_normalize(text)
    norm_old, _ = _ws_normalize(old_text)
    spans: list[tuple[int, int]] = []
    if not norm_old:
        return spans
    pos = 0
    while True:
        idx = norm_text.find(norm_old, pos)
        if idx < 0:
            return spans
        spans.append((tmap[idx][0], tmap[idx + len(norm_old) - 1][1]))
        pos = idx + 1


def _escape_spans(text: str, old_text: str) -> list[tuple[int, int]]:
    unescaped = old_text
    for raw, lit in _ESCAPE_MAP.items():
        unescaped = unescaped.replace(raw, lit)
    if unescaped == old_text:
        return []
    # the unescaped needle goes through line-ending-tolerant matching too:
    # a literal "\n" in the needle still has to land on a CRLF file
    return _exact_spans(text, unescaped) or _whitespace_spans(text, unescaped)


#: The ladder, in degradation order. Each entry: (level name, span finder)
CHAIN: list[tuple[str, Finder]] = [
    ("exact", _exact_spans),
    ("line_trimmed", _line_trimmed_spans),
    ("block_anchor", _block_anchor_spans),
    ("whitespace", _whitespace_spans),
    ("escape", _escape_spans),
]


def locate(text: str, old_text: str) -> MatchResult:
    """Walk the chain and accept only a unique match at the least-degraded
    level. Ambiguity at any level is reported with the highest candidate
    count seen, but never accepted."""
    best_ambiguous = 0
    for level, finder in CHAIN:
        spans = finder(text, old_text)
        if len(spans) == 1:
            indent = None
            consumed_eol = False
            if level == "line_trimmed":
                if old_text[:1] not in (" ", "\t", ""):
                    # old_text is unindented while the file line may not be:
                    # expose the file's indent so the caller can reindent
                    indent = _first_line_indent(text, spans[0]) or None
                # a trailing "" in old_text makes the span swallow the file's
                # terminator; the caller must keep one line break in place
                consumed_eol = (
                    old_text.endswith("\n") and text[spans[0][1] - 1 : spans[0][1]] == "\n"
                )
            return MatchResult(spans[0], level, 0, indent, consumed_eol)
        best_ambiguous = max(best_ambiguous, len(spans))
    return MatchResult(None, None, best_ambiguous)


def _first_line_indent(text: str, span: tuple[int, int]) -> str:
    """Leading whitespace of the first content line inside the span (skipping
    the consumed leading newline, when the span starts on one)."""
    seg = text[span[0] : span[1]]
    if seg.startswith("\r\n"):
        seg = seg[2:]
    elif seg and seg[0] in "\r\n":
        seg = seg[1:]
    match = re.match(r"[ \t]*", seg)
    return match.group(0) if match else ""


def reindent(new_text: str, indent: str) -> str:
    """Prepend the matched line's indentation to every non-empty line of
    new_text, so a whole-line fuzzy replacement keeps the file's block
    indentation."""
    if not indent:
        return new_text
    return "\n".join(indent + part if part else part for part in new_text.split("\n"))


__all__ = ["CHAIN", "MatchResult", "locate", "reindent"]
