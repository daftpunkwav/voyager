"""Text conventions within the sources service: LIKE escaping and tag
character rules.

Other services keep their own local implementations; this module only
deduplicates repetition inside sources, it is not a general toolbox.
"""

from __future__ import annotations

_TAG_CHARS = set('[]"\\,')


def escape_like(s: str) -> str:
    """Escape LIKE metacharacters: backslash, %, _."""
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def valid_tag(tag: str) -> bool:
    """Tag rules: non-empty, <= 32 chars, no JSON-array reserved characters."""
    return bool(tag) and len(tag) <= 32 and not (_TAG_CHARS & set(tag))
