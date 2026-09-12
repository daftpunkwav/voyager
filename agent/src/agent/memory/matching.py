"""Retrieval matching: query tokenization and multi-term scoring.

Search previously LIKE-matched whole strings - "graph db" could not find
"graphdb", so multi-word queries almost always missed. Terms are now split
on whitespace: the SQL layer OR-fetches candidates per term, and the Python
layer scores by the number of distinct terms hit, full coverage first, ties
broken by recency. Pure LIKE plus scoring; no embedding dependency.
"""

from __future__ import annotations


def split_terms(query: str) -> list[str]:
    """Split on whitespace; degenerate inputs stay sane (no whitespace /
    all-whitespace): a non-empty whole string is one term, an empty string
    yields none."""
    terms = [t for t in (s.strip() for s in query.split()) if t]
    return terms


def like_pattern(term: str) -> str:
    """LIKE pattern: escape %/_/\\ as literals per the ESCAPE rule."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def score(terms: list[str], haystacks: list[str]) -> int:
    """Number of distinct terms hit (case-insensitive): a term counts once it
    appears in any field."""
    joined = "\n".join(haystacks).lower()
    return sum(1 for t in terms if t.lower() in joined)


__all__ = ["like_pattern", "score", "split_terms"]
