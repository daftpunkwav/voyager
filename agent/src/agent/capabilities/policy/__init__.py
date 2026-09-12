"""Policy capability group (approval-memory transparency and revocation).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.policy.list_approvals import register as _list_approvals
from agent.capabilities.policy.revoke_approval import register as _revoke_approval


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _list_approvals(reg, deps)
    _revoke_approval(reg, deps)
