"""Policy decision result: the one value type every dimension returns.

Leaf module (imports only levels) so the dimension files and the engine
facade can both depend on it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.policy.levels import Level


@dataclass(frozen=True)
class Decision:
    allow: bool
    level: Level = Level.L0_SILENT
    reason: str = ""


__all__ = ["Decision"]
