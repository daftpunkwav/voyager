"""Prompt prefix stability diagnostics for provider prefix caches.

Providers cache the request head (system prompt + tool schemas + oldest
messages): any byte change there re-bills the full input. The builder already
orders layers stable-first (builder.system) and the status line is bucketed
(usage.STATUS_PCT_BUCKET); what is missing is visibility - when the head does
change turn-over-turn, nothing says which segment moved. PrefixWatch hashes
the system prompt and the activated tool roster each turn and emits one debug
line per changed segment on the "agent.context.prefix" logger, so an operator
auditing cache behavior can enable that logger and see exactly what breaks
the prefix.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable

log = logging.getLogger("agent.context.prefix")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class PrefixWatch:
    """Per-instance sentinel over the request head; the first observation
    only sets the baseline, later segment changes log one line each."""

    def __init__(self) -> None:
        self._system = ""
        self._tools = ""

    def observe(self, *, system: str, tools: Iterable[str]) -> None:
        """Fold one turn's head; logs on each segment change after the
        baseline turn. Tool order is normalized (sorted) so registry copy
        order alone never reads as a change."""
        system_hash = _hash(system)
        if system_hash != self._system:
            if self._system:
                log.debug(
                    "system prompt changed (%s -> %s): prefix cache invalidates"
                    " from the system layer",
                    self._system,
                    system_hash,
                )
            self._system = system_hash
        tools_hash = _hash("\n".join(sorted(tools)))
        if tools_hash != self._tools:
            if self._tools:
                log.debug(
                    "tool roster changed (%s -> %s): prefix cache invalidates"
                    " from the tools segment",
                    self._tools,
                    tools_hash,
                )
            self._tools = tools_hash


__all__ = ["PrefixWatch"]
