"""Actor call context propagated along the service-call chain.

Responsibilities:
- Carry actor identity plus trace_id across every hop of an interaction
- has_scope: scope checks for capability invocation
- restrict: derive a strictly narrower context (scope intersection)

No hop in the chain may escalate privileges; contexts can only narrow.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from platform_contracts import ActorRef, new_trace_id

WILDCARD = "*"  # full-access scope


@dataclass(frozen=True)
class ActorContext:
    """Actor context for one call chain.

    trace_id is carried across every process involved in an interaction.
    """

    actor: ActorRef
    trace_id: str = field(default_factory=new_trace_id)

    def has_scope(self, scope: str) -> bool:
        return WILDCARD in self.actor.scopes or scope in self.actor.scopes

    def restrict(self, scopes: Iterable[str]) -> ActorContext:
        """Derive a strictly narrower context.

        Intersects the held scopes with the requested ones; a "*" holder is
        narrowed to exactly the requested scopes.
        """
        requested = set(scopes)
        if WILDCARD in self.actor.scopes:
            narrowed = tuple(sorted(requested))
        else:
            narrowed = tuple(sorted(set(self.actor.scopes) & requested))
        return ActorContext(actor=replace(self.actor, scopes=narrowed), trace_id=self.trace_id)
