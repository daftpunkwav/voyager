"""revoke_approval capability: drop remembered L2 grants (empty field =
wildcard). Management of the approval memory is the user's prerogative — it
widens the agent's own permission envelope, so this stays human-only (see
the parity exception list)."""

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
        name="revoke_approval",
        description="Revoke remembered L2 approvals (tool and/or target; empty = all)",
        cost=1,
    )
    def revoke_approval(tool: str = "", target: str = "", _actor: ActorRef | None = None) -> dict:
        _require_user(_actor)
        return {"revoked": deps.approvals.revoke(tool=tool, target=target)}
