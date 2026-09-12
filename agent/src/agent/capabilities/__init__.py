"""Agent capability registration package.

One capability per file under capabilities/<group>/<name>.py (file name =
capability name); each group's __init__ and registry.py only aggregate.
Public entry points:
    from agent.capabilities import CapabilityDeps, build_agent_registry
"""

from __future__ import annotations

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.registry import build_agent_registry

__all__ = ["CapabilityDeps", "build_agent_registry"]
