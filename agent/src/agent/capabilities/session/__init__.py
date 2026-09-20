"""Session capability group (chat-session management, the human path).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.session.session import register as _session


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _session(reg, deps)
