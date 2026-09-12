"""Capability registry: the single source of truth for a
service's capabilities.

Responsibilities:
- register / get / names / all: the per-service capability table
- merge(): fold sub-module registries into an aggregate registry

For aggregate domains, the aggregate registry is the merge of the
sub-module registries; the aggregation layer itself has zero logic.
Conflicts raise immediately instead of silently overwriting.
"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

from platform_capability.define import Capability


class Registry:
    """Capability registry of one service (or sub-module). The domain is the
    error-code prefix (e.g. ``example`` -> ``EXAMPLE.*``)."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._items: dict[str, Capability] = {}

    def register(self, cap: Capability) -> Capability:
        if cap.name in self._items:
            raise ServiceError(
                self.domain, ErrorSuffix.CONFLICT, f"duplicate capability registration: {cap.name}"
            )
        self._items[cap.name] = cap
        return cap

    def merge(self, *others: Registry) -> None:
        """Merge sub-module registries (for aggregate services). Name
        conflicts raise immediately."""
        for other in others:
            for cap in other.all():
                self.register(cap)

    def get(self, name: str) -> Capability:
        try:
            return self._items[name]
        except KeyError:
            raise ServiceError(
                self.domain,
                ErrorSuffix.NOT_FOUND,
                f"unknown capability: {name}",
                hint="GET /capabilities lists all capabilities of this service",
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def all(self) -> list[Capability]:
        return [self._items[n] for n in self.names()]

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)
