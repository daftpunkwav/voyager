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
    #: Why an L2_CONFIRM was raised; the invoke layer retires the confirm
    #: dialog everywhere except writes into user-configured fs write_roots
    #: (the one kept confirmation). Empty for every other decision.
    confirm_scope: str = ""


__all__ = ["Decision"]
