"""tools capability: the tool roster's self-management surface — one action
parameter covers list/describe/search. The agent's tools tool binds this
same capability."""

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
        name="tools",
        description=(
            "Tool-surface self-management: action list (roster with dimension/"
            "write/class metadata), describe (name — full metadata with schema), "
            "search (query,limit — lexical match; use before activate_tools)"
        ),
    )
    def tools(action: str = "list", name: str = "", query: str = "", limit: int = 8) -> dict | list:
        if action == "list":
            # Roster matches the ToolSpec the LLM sees (built-in tools + domain
            # bridges such as notes__*); parameter schemas stay out of the
            # list (token volume) and live behind describe.
            return deps.toolbelt.roster()
        if action == "describe":
            return deps.toolbelt.describe(name)
        if action == "search":
            roster = [{"name": s.name, "description": s.description} for s in deps.toolbelt.specs()]
            return rank_tools(roster, query, limit=limit)
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r}",
            hint="valid actions: list/describe/search",
        )
