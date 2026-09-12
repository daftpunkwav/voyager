"""Start / stop / close of wired domains with rollback.

Start follows wire (insertion) order. Stop and close run in reverse so
dependents shut down before their dependencies. A failure mid-start stops
whatever already started; a failure mid-stop or mid-close is logged and the
rest still run so one broken domain cannot pin the process open.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from platform_capability import Wiring

log = logging.getLogger("host.lifecycle")


async def start_wirings(wirings: Mapping[str, Wiring]) -> list[Wiring]:
    """Start each wiring in insertion order. On failure, stop those already
    started (reverse order) and re-raise."""
    started: list[Wiring] = []
    try:
        for domain, wiring in wirings.items():
            if wiring.start:
                await wiring.start()
            started.append(wiring)
            log.debug("domain started: %s", domain)
        return started
    except BaseException:
        await stop_wirings(started)
        raise


async def stop_wirings(wirings: Sequence[Wiring]) -> None:
    """Stop wirings in reverse order. Individual stop failures are isolated."""
    for wiring in reversed(list(wirings)):
        if not wiring.stop:
            continue
        try:
            await wiring.stop()
        except Exception:
            log.exception("domain stop failed")


def close_wirings(wirings: Sequence[Wiring]) -> None:
    """Close wirings in reverse order. Individual close failures are isolated."""
    for wiring in reversed(list(wirings)):
        if not wiring.close:
            continue
        try:
            wiring.close()
        except Exception:
            log.exception("domain close failed")


def close_quietly(closer: object, *, what: str) -> None:
    """Call ``close()`` on a shared facility; never raise to the caller."""
    close = getattr(closer, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        log.exception("close failed: %s", what)
