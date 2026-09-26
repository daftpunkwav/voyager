"""Prompt prefix cache sentinel: stability diagnostics, break detection and
culprit localization for provider prefix caches.

Providers cache the request head (system prompt + tool schemas + oldest
messages): any byte change there re-bills the full input. The builder already
orders layers stable-first (builder.system) and the status line is bucketed
(usage.STATUS_PCT_BUCKET). PrefixWatch adds the missing feedback loop:

- Turn-level stability (``observe``): hashes the system prompt and the
  activated tool roster each turn; a changed segment logs one line naming it.
- Round-level cache health (``observe_round``): folds each completion's
  provider-reported usage. A cold round (cached_tokens == 0 on a sizable
  input) *after* a warm one was seen is a prefix-cache break; when the
  harness-visible head is unchanged too, the break is unexplained (likely
  provider-side) and lands in the health counters, not just a log line.
- Localization: when the head did change, the per-message hash diff names
  the first message index that moved, so an operator (or the model itself,
  via context_status) sees exactly what re-billed the prefix.

All logging goes to the "agent.context.prefix" logger (debug for expected
churn, warning for unexplained breaks); the numeric counters live in
``health()`` for telemetry surfaces.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Sequence

log = logging.getLogger("agent.context.prefix")

#: Minimum input size (tokens) before a cold round counts as a break: small
#: requests are re-billed trivially and early rounds are legitimately cold
_MISS_THRESHOLD_TOKENS = 1000

#: How many head messages (after the system entry) the per-message diff tracks
_HEAD_DEPTH = 8


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class PrefixWatch:
    """Per-instance sentinel over the request head and its cache health.

    The first observation only sets the baseline. Later segment changes log
    one line each; cold-after-warm rounds with no harness-visible change
    count as unexplained misses in ``health()``.
    """

    def __init__(self) -> None:
        self._system = ""
        self._tools = ""
        self._head: list[str] | None = None  # per-message hashes; None = no baseline yet
        self._ever_warm = False  # a cached_tokens > 0 round was seen
        self._pending_change = ""  # turn-level segment change not yet folded into a round
        self.turns = 0
        self.warm_rounds = 0
        self.cold_rounds = 0
        self.unexplained_misses = 0
        self.changes: dict[str, int] = {"system": 0, "tools": 0, "messages": 0}
        self.last_break: dict[str, object] | None = None

    # -- turn-level segment stability -----------------------------------------

    def observe(self, *, system: str, tools: Iterable[str], tool_fingerprint: str = "") -> None:
        """Fold one turn's head; logs on each segment change after the
        baseline turn.

        tool_fingerprint (when given) hashes the serialized ACTIVE tool specs
        — schema bytes included, in wire order (specs() is sorted by name, so
        registry copy order alone never reads as a change) — instead of the
        names alone: a schema or graded-activation change is a real
        tools-segment cache break, while the full roster's names stay
        identical. Without it the names-only fallback hashes the sorted
        names."""
        system_hash = _hash(system)
        if system_hash != self._system:
            if self._system:
                self.changes["system"] += 1
                self._pending_change = "system"
                log.debug(
                    "system prompt changed (%s -> %s): prefix cache invalidates"
                    " from the system layer",
                    self._system,
                    system_hash,
                )
            self._system = system_hash
        tools_hash = (
            _hash(tool_fingerprint) if tool_fingerprint else _hash("\n".join(sorted(tools)))
        )
        if tools_hash != self._tools:
            if self._tools:
                self.changes["tools"] += 1
                self._pending_change = self._pending_change or "tools"
                log.debug(
                    "tool roster changed (%s -> %s): prefix cache invalidates"
                    " from the tools segment",
                    self._tools,
                    tools_hash,
                )
            self._tools = tools_hash
        self.turns += 1

    # -- round-level cache health ---------------------------------------------

    def observe_round(
        self,
        *,
        input_tokens: int,
        cached_tokens: int,
        messages: Sequence[dict[str, object]] = (),
    ) -> None:
        """Fold one completion's usage plus the request body it went out with.

        A cold round after a warm one is a prefix-cache break: explained when
        a head segment moved since the previous round (the diff names the
        first moved message), unexplained otherwise - the latter counts in
        ``health()`` and logs a warning once per occurrence.
        """
        if cached_tokens > 0:
            self._ever_warm = True
            self.warm_rounds += 1
            self._fold_head(messages)
            self._pending_change = ""
            return
        self.cold_rounds += 1
        if not self._ever_warm or input_tokens < _MISS_THRESHOLD_TOKENS:
            # Cold start or trivially small request: not a break signal
            self._fold_head(messages)
            self._pending_change = ""
            return
        moved = self._fold_head(messages)
        pending = self._pending_change
        self._pending_change = ""
        if moved is None and not pending:
            # No harness-visible change since the warm round: the provider
            # dropped the cache on its side; nothing to heal, but it must
            # not stay invisible
            self.unexplained_misses += 1
            self.last_break = {
                "kind": "unexplained",
                "input_tokens": input_tokens,
            }
            log.warning(
                "prefix cache broke with no harness-visible head change "
                "(input=%d tokens): provider-side eviction or routing change",
                input_tokens,
            )
            return
        culprit = pending or f"message head ({moved})"
        log.info(
            "prefix cache re-billed after an expected head change: %s moved",
            culprit,
        )

    def _fold_head(self, messages: Sequence[dict[str, object]]) -> str | None:
        """Hash the tracked head (first _HEAD_DEPTH body messages); returns a
        description of the first moved message, or None when unchanged (the
        baseline-setting first observation counts as unchanged too)."""
        head = [
            _hash(f"{m.get('role', '')}\n{m.get('content', '')}")
            for m in messages[1 : _HEAD_DEPTH + 1]
        ]
        previous = self._head
        self._head = head
        if previous is None or previous == head:
            return None
        self.changes["messages"] += 1
        for i, (old, new) in enumerate(zip(previous, head)):
            if old != new:
                return f"index {i} changed"
        return f"length {len(previous)} -> {len(head)}"

    # -- telemetry -------------------------------------------------------------

    def health(self) -> dict[str, object]:
        """Numeric cache-health snapshot for context_status / operators."""
        return {
            "turns": self.turns,
            "warm_rounds": self.warm_rounds,
            "cold_rounds": self.cold_rounds,
            "unexplained_misses": self.unexplained_misses,
            "head_changes": dict(self.changes),
            "last_break": self.last_break,
        }


__all__ = ["PrefixWatch"]
