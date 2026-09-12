"""In-app dimension: capability allow/deny lists and the decision function
(split from policy.engine, phase 21)."""

from __future__ import annotations

from dataclasses import dataclass

from agent.policy.decision import Decision
from agent.policy.levels import Level


@dataclass(frozen=True)
class AppPolicy:
    """In-app permissions: capability whitelist (down to individual capabilities); secret
    settings are always denied (enforced at the framework layer)."""

    allowed: frozenset[str] = frozenset({"*"})
    denied: frozenset[str] = frozenset()


def matches_policy(name: str, entries: frozenset[str]) -> bool:
    """Match rule: exact equality, the `*` wildcard, or a trailing-`*` prefix
    (e.g. `notes__*`)."""
    if "*" in entries:
        return True
    if name in entries:
        return True
    prefixes = [e[:-1] for e in entries if e.endswith("*") and len(e) > 1]
    return any(name.startswith(p) for p in prefixes)


def decide_app(app: AppPolicy, action) -> Decision:
    name = action.target
    if matches_policy(name, app.denied):
        return Decision(False, reason=f"Capability explicitly disabled: {name}")
    if not matches_policy(name, app.allowed):
        return Decision(False, reason=f"Capability not in the allowlist: {name}")
    if action.irreversible:
        return Decision(True, Level.L2_CONFIRM, "Irreversible capability requires confirmation")
    return Decision(True, Level.L1_NOTIFY if action.write else Level.L0_SILENT)


__all__ = ["AppPolicy", "decide_app", "matches_policy"]
