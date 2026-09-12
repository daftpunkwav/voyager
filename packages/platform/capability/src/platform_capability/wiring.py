"""Wiring protocol: the shape of a service's assembled artifacts, shared by
standalone mode (rest.py) and aggregate mode (composition root).

Each service provides a `wiring.py` exposing `wire(data_dir, ...) -> Wiring`:
- Standalone: rest.py calls wire() and gets the registry plus lifecycle
  handles, without assembling stores/deps itself.
- Aggregate: the composition root calls the same wire() and mounts the
  registry into the aggregate entry; start/stop/close run in the root's
  unified lifespan.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_capability.registry import Registry

if TYPE_CHECKING:  # fastapi is an optional dependency (mount-side only); not imported at runtime
    from fastapi import APIRouter


@dataclass
class Wiring:
    """The fully wired artifact of one service.

    - registry: capability registry (the sole source for REST mounting, MCP
      generation, and agent tool bridges);
    - probe: health probe (sync or async; None means passive detection only);
    - start/stop: background lifecycle (workers, schedulers, ...), invoked by
      the composition root's lifespan;
    - close: release owned resources (db connections, ...); shared resources
      passed in from outside are not closed here;
    - extra_router: domain-specific routes (e.g. read-only file downloads).
      wire() builds it and hands it to the composition root to pass through
      to the aggregate entry, so the root never touches domain-internal
      stores (integration goes through the protocol, not direct table reads).
    """

    registry: Registry
    probe: Callable[[], dict | Awaitable[dict]] | None = None
    start: Callable[[], Awaitable[None]] | None = None
    stop: Callable[[], Awaitable[None]] | None = None
    close: Callable[[], None] | None = None
    extra_router: APIRouter | None = None
