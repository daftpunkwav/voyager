"""list_approvals capability: view remembered L2 grants (the approval memory
must stay transparent — every "always allow" is inspectable)."""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def _require_user(actor: ActorRef | None) -> None:
    if actor is None or actor.kind is not ActorKind.USER:
        raise ServiceError(
            "agent",
            ErrorSuffix.FORBIDDEN,
            "approval-memory management is a user-only operation",
        )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_approvals",
        description="Remembered L2 approvals (tool + target, session or persistent; revocable)",
    )
    def list_approvals(_actor: ActorRef | None = None) -> list[dict]:
        _require_user(_actor)
        return deps.approvals.list()
