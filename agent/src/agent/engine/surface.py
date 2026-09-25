"""Allowlist-vs-surface matching for dispatch-time narrowing.

The rule (one function family, two callers): when an instance dispatches a
subagent, every requested allowlist entry — explicit spawn parameter, custom
definition, or persona preset — is resolved against the dispatching
instance's effective surface. Entries the surface cannot offer at all are
rejected (readable error, the model corrects its request); the rest is
frozen to the intersection so the child — and a later checkpoint resume —
can narrow but never widen.

Matching follows Toolbelt.trimmed: a trailing `*` (beyond one character) is
a prefix grant expanded against the surface, everything else is an exact
name.
"""

from __future__ import annotations

from collections.abc import Iterable


def _is_prefix(entry: str) -> bool:
    return entry.endswith("*") and len(entry) > 1


def entry_matches(name: str, entry: str) -> bool:
    """Whether one surface name is covered by one allowlist entry."""
    if _is_prefix(entry):
        return name.startswith(entry[:-1])
    return name == entry


def surface_misses(entries: Iterable[str], available: Iterable[str]) -> list[str]:
    """Entries with zero availability on the surface (the dispatch rejects
    listing these). A prefix entry counts as available when at least one
    surface name matches it."""
    names = list(available)
    return [e for e in entries if not any(entry_matches(n, e) for n in names)]


def intersect_surface(entries: Iterable[str], available: Iterable[str]) -> tuple[str, ...]:
    """The effective surface: available names covered by at least one entry,
    in the surface's (sorted) order — deterministic for prompt-cache stable
    schema ordering and identical across checkpoint resumes."""
    wanted = list(entries)
    return tuple(n for n in available if any(entry_matches(n, e) for e in wanted))


__all__ = ["entry_matches", "intersect_surface", "surface_misses"]
