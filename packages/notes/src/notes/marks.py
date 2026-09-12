"""Note body highlight marks (still Markdown): ==tone:text==, not rich text.

Responsibilities:
- Parse, apply, strip, and scan ==tone:text== marks in note bodies
  (parse_mark / wrap_mark / scan_marks / apply_note_mark)
- Wrap multi-line selections per line while leaving heading/list prefixes,
  fenced and inline code, and ASCII structure outside the markers
- Flatten existing marks covered by a larger selection; nested == is not
  allowed

The user toolbar and mark_note_span share this syntax. The module has no
dependency on capabilities, keeping it easy to unit-test and extend.

Multi-line spans (including blank lines) are wrapped per line, with
heading/list prefixes left outside the markers. Fenced and inline code are
never highlighted (code blocks, ASCII diagrams, and literal == stay as-is).
ASCII box-drawing and table lines are never wrapped. Existing marks covered
by a larger selection are flattened before re-wrapping; nested == is not
allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TONES = ("warm", "cool", "rose", "lime", "violet", "sand")
CLEAR = "clear"
QUOTE_MAX = 500
_TONE_KIND = r"warm|cool|rose|lime|violet|sand|rgb[0-9a-fA-F]{6}"
_TONE_AT = re.compile(rf"^({_TONE_KIND}):", re.IGNORECASE)
_TONE_OPEN = re.compile(rf"==({_TONE_KIND}):", re.IGNORECASE)
_RGB = re.compile(r"^rgb[0-9a-f]{6}$")
_HEX6 = re.compile(r"^[0-9a-f]{6}$")

_FENCE_LINE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_BLOCK_PREFIX = re.compile(
    r"^(?:#{1,6}[ \t]+|(?:>[ \t]*)+"
    r"|\s*[-*+][ \t]+\[[ xX]\][ \t]+"
    r"|\s*[-*+][ \t]+"
    r"|\s*\d+[.)][ \t]+)"
)


class MarkError(ValueError):
    """Invalid highlight arguments, or the quoted span is not found in the body."""


@dataclass(frozen=True)
class MarkSpan:
    start: int
    inner_start: int
    inner_end: int
    end: int
    tone: str


@dataclass
class TextSpan:
    start: int
    end: int
    kind: str  # text | fence
    tone: str | None


def normalize_tone(tone: str) -> str:
    """Accepts warm / rgb7c3aed / #7c3aed / 7c3aed / clear; raises MarkError otherwise."""
    raw = (tone or "").strip().lower()
    raw = raw.removeprefix("#")
    if raw in TONES or raw == CLEAR:
        return raw
    if _RGB.fullmatch(raw):
        return raw
    if _HEX6.fullmatch(raw):
        return "rgb" + raw
    raise MarkError(f"tone must be one of {list(TONES)}, rgbRRGGBB / #RRGGBB / RRGGBB, or {CLEAR}")


def _read_tone_at(text: str, inner_from: int) -> tuple[str, int] | None:
    matched = _TONE_AT.match(text[inner_from:])
    if not matched:
        return None
    return matched.group(1).lower(), inner_from + matched.end()


def parse_mark(text: str) -> tuple[str, str] | None:
    """Parse a full mark into (tone, inner); None if unrecognized.

    An inner text containing == is treated as an unclosed span.
    """
    if not text:
        return None
    if text.startswith("==") and text.endswith("==") and len(text) >= 4:
        body = text[2:-2]
        if "==" in body:
            return None
        hit = _read_tone_at(body, 0)
        if hit:
            tone, inner_start = hit
            return tone, body[inner_start:]
        return "warm", body
    return None


def split_prefix(line: str) -> tuple[str, str]:
    if _parse_fence(line):
        return line, ""
    matched = _BLOCK_PREFIX.match(line)
    if not matched:
        return "", line
    return matched.group(0), line[matched.end() :]


def _parse_fence(line: str) -> tuple[str, int, str] | None:
    matched = _FENCE_LINE.match(line)
    if not matched:
        return None
    ticks, rest = matched.group(2), matched.group(3)
    return ticks[0], len(ticks), rest


def _flatten_toned(text: str) -> str:
    s = text
    for _ in range(32):
        marks = scan_marks(s, toned_only=True)
        if not marks:
            break
        for m in reversed(marks):
            s = s[: m.start] + s[m.inner_start : m.inner_end] + s[m.end :]
    s = _TONE_OPEN.sub("", s)
    return re.sub(r"(^|[^=])==(?!=)", r"\1", s)


def _structural_line(line: str) -> bool:
    t = line.strip()
    if not t:
        return False
    if re.match(r"^[+┌├└┬┴][-─=━]{2,}", t):
        return True
    if re.match(r"^[+=\-─━]{4,}$", t):
        return True
    return t.startswith(("|", "│"))


def wrap_line(line: str, tone: str) -> str:
    if _parse_fence(line) or _structural_line(line):
        return line
    prefix, rest = split_prefix(line)
    if _structural_line(rest):
        return line
    body = _flatten_toned(rest)
    if not body.strip():
        return prefix + body
    parsed = parse_mark(body)
    if parsed and parsed[0] == tone:
        return prefix + body if prefix else line
    inner = parsed[1] if parsed else body
    if not inner or "==" in inner:
        return prefix + body
    return prefix + _token(inner, tone)


def _token(inner: str, tone: str) -> str:
    return f"=={tone}:{inner}=="


def wrap_mark(inner: str, tone: str) -> str:
    """inner may span lines: color per line so Markdown does not break cross-line ==."""
    return "\n".join(wrap_line(line, tone) for line in inner.split("\n"))


def fence_ranges(content: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    n = len(content)
    pos = 0
    in_fence = False
    start = 0
    marker = ""
    min_len = 0
    while pos <= n:
        nl = content.find("\n", pos)
        line_end = n if nl < 0 else nl
        parsed = _parse_fence(content[pos:line_end])
        if parsed:
            ch, length, rest = parsed
            if not in_fence:
                in_fence, marker, min_len, start = True, ch, length, pos
            elif ch == marker and length >= min_len and rest.strip() == "":
                ranges.append((start, line_end))
                in_fence = False
        if nl < 0:
            break
        pos = nl + 1
    if in_fence:
        ranges.append((start, n))
    return ranges


def scan_marks(text: str, toned_only: bool = False) -> list[MarkSpan]:
    out: list[MarkSpan] = []
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i : i + 2] != "==":
            i += 1
            continue
        tone = "warm"
        inner_start = i + 2
        toned = False
        hit = _read_tone_at(text, i + 2)
        if hit:
            tone, inner_start = hit
            toned = True
        if toned_only and not toned:
            i += 1
            continue
        close = text.find("==", inner_start)
        if close < 0:
            i += 1
            continue
        if close == inner_start:
            i = close
            continue
        out.append(MarkSpan(i, inner_start, close, close + 2, tone))
        i = close + 2
    return out


def _in_ranges(ranges: list[tuple[int, int]], idx: int) -> bool:
    return any(a <= idx < b for a, b in ranges)


def _inline_code_ranges(content: str, fences: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    n = len(content)
    i = 0
    while i < n:
        if _in_ranges(fences, i) or content[i] != "`":
            i += 1
            continue
        run = 1
        while i + run < n and content[i + run] == "`":
            run += 1
        j = i + run
        found = False
        while j < n:
            if _in_ranges(fences, j):
                break
            if content[j] == "`":
                m = 1
                while j + m < n and content[j + m] == "`":
                    m += 1
                if m == run:
                    ranges.append((i, j + m))
                    i = j + m
                    found = True
                    break
                j += m
                continue
            j += 1
        if not found:
            i += run
    return ranges


def protected_ranges(content: str) -> list[tuple[int, int]]:
    fences = fence_ranges(content)
    return sorted(fences + _inline_code_ranges(content, fences))


def find_marks(content: str) -> list[MarkSpan]:
    fences = protected_ranges(content)
    if not fences:
        return scan_marks(content, toned_only=True)
    out: list[MarkSpan] = []
    pos = 0
    for start, end in fences:
        if start > pos:
            for m in scan_marks(content[pos:start], toned_only=True):
                out.append(
                    MarkSpan(
                        m.start + pos, m.inner_start + pos, m.inner_end + pos, m.end + pos, m.tone
                    )
                )
        pos = end
    if pos < len(content):
        for m in scan_marks(content[pos:], toned_only=True):
            out.append(
                MarkSpan(m.start + pos, m.inner_start + pos, m.inner_end + pos, m.end + pos, m.tone)
            )
    return out


def _in_fence(content: str, idx: int) -> bool:
    return _in_ranges(protected_ranges(content), idx)


def build_spans(doc: str) -> list[TextSpan]:
    fences = fence_ranges(doc)
    marks = find_marks(doc)
    spans: list[TextSpan] = []
    n = len(doc)
    pos = 0
    fi = 0
    mi = 0
    while pos < n:
        fence = fences[fi] if fi < len(fences) and fences[fi][0] == pos else None
        if fence:
            spans.append(TextSpan(fence[0], fence[1], "fence", None))
            pos = fence[1]
            fi += 1
            continue
        mark = marks[mi] if mi < len(marks) and marks[mi].start == pos else None
        if mark:
            spans.append(TextSpan(mark.inner_start, mark.inner_end, "text", mark.tone))
            pos = mark.end
            mi += 1
            continue
        nxt = n
        if fi < len(fences):
            nxt = min(nxt, fences[fi][0])
        if mi < len(marks):
            nxt = min(nxt, marks[mi].start)
        spans.append(TextSpan(pos, nxt, "text", None))
        pos = nxt
    return [s for s in spans if s.end > s.start]


def _split_spans(spans: list[TextSpan], points: list[int]) -> list[TextSpan]:
    cuts = sorted(set(points))
    out: list[TextSpan] = []
    for s in spans:
        if s.kind == "fence":
            out.append(s)
            continue
        inner = [p for p in cuts if s.start < p < s.end]
        a = s.start
        for p in inner:
            out.append(TextSpan(a, p, "text", s.tone))
            a = p
        out.append(TextSpan(a, s.end, "text", s.tone))
    return [s for s in out if s.end > s.start]


def _has_wrappable(doc: str, s: TextSpan) -> bool:
    if s.kind != "text" or s.end <= s.start:
        return False
    for line in doc[s.start : s.end].split("\n"):
        _, rest = split_prefix(line)
        if rest.strip() and "==" not in rest:
            return True
    return False


def _strip_all_marks(text: str) -> str:
    s = text
    for _ in range(32):
        marks = scan_marks(s, toned_only=True)
        if not marks:
            break
        for m in reversed(marks):
            s = s[: m.start] + s[m.inner_start : m.inner_end] + s[m.end :]
    return _TONE_OPEN.sub("", s)


def _emit_spans(
    doc: str,
    spans: list[TextSpan],
    clear_range: tuple[int, int] | None = None,
) -> str:
    parts: list[str] = []
    i = 0
    n = len(spans)
    while i < n:
        s = spans[i]
        if s.kind == "fence":
            raw = doc[s.start : s.end]
            if clear_range and s.end > clear_range[0] and s.start < clear_range[1]:
                parts.append(_strip_all_marks(raw))
            else:
                parts.append(raw)
            i += 1
            continue
        chunks = [s]
        i += 1
        while i < n and spans[i].kind == "text" and spans[i].tone == s.tone:
            chunks.append(spans[i])
            i += 1
        text = "".join(doc[c.start : c.end] for c in chunks)
        if not s.tone:
            if clear_range and any(
                c.end > clear_range[0] and c.start < clear_range[1] for c in chunks
            ):
                parts.append(_strip_all_marks(text))
            else:
                parts.append(text)
        else:
            parts.append("\n".join(wrap_line(line, s.tone) for line in text.split("\n")))
    return "".join(parts)


def apply_in_range(doc: str, start: int, end: int, action: str, *, toggle_same: bool = True) -> str:
    """Apply (color) or clear the highlight over [start, end). Fences are untouched;
    existing marks under the range are flattened first.

    toggle_same: True for the user toolbar (clicking the same tone removes it);
    mark_note_span passes False so re-marking an already-colored span is idempotent.
    """
    if start > end:
        start, end = end, start
    if start == end:
        return doc
    start = max(0, start)
    end = min(len(doc), end)
    inlines = _inline_code_ranges(doc, fence_ranges(doc))
    if any(a <= start and end <= b for a, b in inlines):
        return doc
    marks = find_marks(doc)
    containers = [m for m in marks if m.start <= start and end <= m.end]
    if len(containers) == 1:
        m = containers[0]
        in_inner = m.inner_start <= start and end <= m.inner_end
        proper = start > m.inner_start or end < m.inner_end
        if in_inner and proper and action != CLEAR and action != m.tone:
            left = doc[m.inner_start : start]
            mid = doc[start:end]
            right = doc[end : m.inner_end]
            pieces = [
                wrap_mark(left, m.tone) if left else "",
                wrap_mark(mid, action),
                wrap_mark(right, m.tone) if right else "",
            ]
            return doc[: m.start] + "".join(pieces) + doc[m.end :]
        if action == CLEAR or (toggle_same and action == m.tone):
            return doc[: m.start] + doc[m.inner_start : m.inner_end] + doc[m.end :]
        if action == m.tone:
            return doc
        return doc[: m.start] + wrap_mark(doc[m.inner_start : m.inner_end], action) + doc[m.end :]

    spans = _split_spans(build_spans(doc), [start, end])
    inside = [s for s in spans if s.kind == "text" and s.start >= start and s.end <= end]
    already = (
        action != CLEAR
        and any(_has_wrappable(doc, s) for s in inside)
        and all((not _has_wrappable(doc, s)) or s.tone == action for s in inside)
    )
    for s in spans:
        if s.kind == "fence":
            continue
        if s.start >= start and s.end <= end:
            if action == CLEAR or (toggle_same and already):
                s.tone = None
            elif not already:
                s.tone = action
    return _emit_spans(doc, spans, (start, end) if action == CLEAR else None)


def _visible_map(content: str) -> tuple[str, list[int]]:
    """Visible text (mark delimiters removed, fence content kept) -> source index map."""
    delim: set[int] = set()
    for m in find_marks(content):
        delim.update(range(m.start, m.inner_start))
        delim.update(range(m.inner_end, m.end))
    chars: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(content):
        if i not in delim:
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


def apply_note_mark(content: str, quote: str, tone: str) -> str:
    """Color or clear the first occurrence of quote outside fences/inline code.

    Idempotent when the span already has the target tone.
    """
    tone = normalize_tone(tone)
    raw = quote or ""
    if not raw.strip():
        raise MarkError("quote cannot be empty")
    if len(raw) > QUOTE_MAX:
        raw = raw[:QUOTE_MAX]

    parsed = parse_mark(raw)
    needle = parsed[1] if parsed else raw
    if not needle or not needle.strip():
        raise MarkError("Span is empty or contains ==")

    visible, src_of = _visible_map(content)
    start_vis = 0
    found_from = -1
    found_to = -1
    while True:
        idx = visible.find(needle, start_vis)
        if idx < 0:
            break
        src_from = src_of[idx]
        src_to = src_of[idx + len(needle) - 1] + 1
        if not _in_fence(content, src_from):
            found_from, found_to = src_from, src_to
            break
        start_vis = idx + 1
    if found_from < 0:
        raise MarkError("Span not found in the content")

    return apply_in_range(content, found_from, found_to, tone, toggle_same=False)
