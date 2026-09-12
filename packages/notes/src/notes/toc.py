"""Markdown ATX heading outline extraction, matching the frontend
extractNoteToc semantics.
"""

from __future__ import annotations

import re
from typing import Any


def extract_toc(content: str) -> list[dict[str, Any]]:
    """Extract a Markdown heading outline (ATX levels 1-6).

    Returns dicts with level/text/line (1-based line numbers over LF text).
    Used by the frontend outline panel and scroll positioning. `#` runs
    inside fenced code blocks are not headings, so fenced sections are
    skipped.
    """
    toc: list[dict[str, Any]] = []
    in_fence = False
    fence_marker = ""
    for line_no, line in enumerate(content.split("\n"), start=1):
        stripped = line.lstrip()
        if stripped[:3] in ("```", "~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence or not stripped.startswith("#"):
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if m:
            toc.append({"level": len(m.group(1)), "text": m.group(2).strip(), "line": line_no})
    return toc
