"""search_tools capability: lexical lookup over the current tool roster.

With domain bridges and mounted MCP servers the roster can hold dozens of
tools whose schemas are only shown after activation (graded loading) - the
model needs a way to find the right name without dumping every description
into context. Simple term scoring: hits in the tool name weigh above hits in
the description; a tool matches when at least one query term hits. This is
plain lexical matching, not BM25.
"""

from __future__ import annotations

import re

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps

#: Tokenization units: ascii words, single CJK ideographs
_TERM_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]")

#: Scoring weights: a name hit is worth more than a description hit
_NAME_WEIGHT = 2
_DESC_WEIGHT = 1


def _terms(text: str) -> list[str]:
    return [t.lower() for t in _TERM_RE.findall(text)]


def rank_tools(roster: list[dict], query: str, *, limit: int = 8) -> list[dict]:
    """Score the roster against the query; returns entries with a positive
    score, best first, each carrying its score for transparency."""
    terms = _terms(query)
    if not terms:
        return []
    scored: list[dict] = []
    for entry in roster:
        name = str(entry.get("name") or "").lower()
        desc = str(entry.get("description") or "").lower()
        score = 0
        for term in terms:
            if term in name:
                score += _NAME_WEIGHT
            if term in desc:
                score += _DESC_WEIGHT
        if score > 0:
            scored.append({**entry, "score": score})
    scored.sort(key=lambda e: (-e["score"], str(e.get("name") or "")))
    return scored[: max(1, int(limit))]


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="search_tools",
        description=(
            "Find tools on the current roster by keyword (lexical match on name"
            " and description); use before activate_tools when the exact name is"
            " unknown"
        ),
    )
    def search_tools(query: str, limit: int = 8) -> list[dict]:
        roster = [{"name": s.name, "description": s.description} for s in deps.toolbelt.specs()]
        return rank_tools(roster, query, limit=limit)
