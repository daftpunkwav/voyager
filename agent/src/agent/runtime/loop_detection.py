"""ReAct loop detection: a sliding window that spots repeated tool calls.

When the model gets stuck (the same tool called with the same arguments over and over), a
brute-force max_rounds cutoff burns a full round of budget before stopping; this module
declares a loop as soon as the same signature reaches the threshold within the window.
A signature is tool name + canonicalized argument JSON (key-order independent). The detector
is a per-turn instance with no cross-turn memory -- legitimate cross-turn repetition (e.g.
a daily weather check) must not be flagged.

Bookkeeping tools (todo list updates and the like) are transparent to the window: they
are neither counted nor do they evict substantive calls, so interleaved bookkeeping
cannot dilute or wash a repetition pattern.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

#: Sliding window size and threshold: a loop is declared when the same signature appears
#: >= 3 times in the last 6 calls
DEFAULT_WINDOW = 6
DEFAULT_THRESHOLD = 3

#: Bookkeeping tools invisible to the detector: legitimate todo updates repeat by
#: design, and counting them would both false-trip and let interleaved updates evict
#: a real repetition pattern from the window
BOOKKEEPING_TOOLS = frozenset({"todowrite"})


class LoopDetector:
    """Sliding-window loop detection by call signature; record returning True means the
    threshold is reached and the turn should be interrupted."""

    def __init__(
        self,
        *,
        window: int = DEFAULT_WINDOW,
        threshold: int = DEFAULT_THRESHOLD,
        bookkeeping: frozenset[str] = BOOKKEEPING_TOOLS,
    ) -> None:
        self._window = window
        self._threshold = threshold
        self._bookkeeping = bookkeeping
        self._recent: deque[str] = deque(maxlen=window)

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def window(self) -> int:
        return self._window

    @staticmethod
    def signature(name: str, arguments: dict[str, Any]) -> str:
        """Tool name + canonicalized argument JSON (key-order independent; non-JSON values
        fall back to str)."""
        canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        return f"{name}|{canonical}"

    def record(self, name: str, arguments: dict[str, Any]) -> bool:
        """Record one call; returns True once the signature appears threshold times in the
        window. Calls are counted before execution, so rejected and failed calls count
        too. Bookkeeping calls return False immediately and leave the window untouched."""
        if name in self._bookkeeping:
            return False
        sig = self.signature(name, arguments)
        self._recent.append(sig)
        return self._recent.count(sig) >= self._threshold


__all__ = ["BOOKKEEPING_TOOLS", "DEFAULT_THRESHOLD", "DEFAULT_WINDOW", "LoopDetector"]
