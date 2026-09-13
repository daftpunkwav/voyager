"""Context budget assembly: settings -> ContextBudget.

Same pattern as subagent.limits: built-in constants are the floor, the
settings keys hot-read on every use, and a dirty/unset value falls back to
the built-in default. The budget travels with the instance so history
bounding, transcript compaction, and resume snapshots all share one value.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.usage import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_WINDOW_TOKENS,
    resolve_window,
)
from agent.contracts import SettingsReader

#: Hard cap on cross-turn history length (entries): long conversations must
#: not grow without bound. History holds only user/assistant entries (tool
#: entries live in messages for the current turn only), dropped in pairs.
#: Defined here (not on the instance) so the whole context budget lives in
#: one place; the instance re-exports it for compatibility.
HISTORY_MAX = 60

#: Resident memory-card layer defaults: how many recent episodic entries the
#: system prompt carries and the character cap of the whole layer (0 = off).
MEMORY_CARDS = 5
MEMORY_CARD_CHARS = 600

#: Resident relevance layer defaults (memory read policy): how many recall
#: hits the system prompt carries for the current input and the character cap
#: of the layer (0 = off). Bounded so the relevance layer never crowds out
#: the transcript itself.
RECALL_FACTS = 4
RECALL_CHARS = 600


@dataclass(frozen=True)
class ContextBudget:
    """Per-instance context budget (token estimates, not bytes).

    history_max / compress_budget are the classic bounds; the window fields
    carry the resolved per-model limits so the usage status and the
    auto-compact trigger share one snapshot with the rest of the budget.
    """

    history_max: int = HISTORY_MAX  # cross-turn user/assistant entries
    compress_budget: int = COMPRESS_BUDGET  # per-turn mechanical fallback budget
    window_tokens: int = DEFAULT_WINDOW_TOKENS  # model context window
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS  # room reserved for the reply
    auto_compact_at: int = 75  # percent of usable window that triggers LLM compaction
    compact_target: int = 0  # post-compact target; 0 = auto (40% of usable window)
    memory_cards: int = MEMORY_CARDS  # recent episodic cards resident in the system layer
    memory_card_chars: int = MEMORY_CARD_CHARS  # character cap of that layer
    recall_facts: int = RECALL_FACTS  # relevance-layer hits for the current input
    recall_chars: int = RECALL_CHARS  # character cap of that layer


def budget_from_settings(settings: SettingsReader, model_name: str = "") -> ContextBudget:
    """Hot-read the budget keys; non-positive or malformed values count as
    unset and fall back to the built-in defaults.

    model_name selects the per-model window profile
    (agent.context.model_profiles); empty or unknown names use the globals.
    """

    def _int(key: str, fallback: int) -> int:
        try:
            value = int(settings.get(key))
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    def _int_or_zero(key: str, fallback: int) -> int:
        """Like _int but an explicit 0 is a valid "off" value, not unset."""
        try:
            value = int(settings.get(key))
        except (TypeError, ValueError):
            return fallback
        return value if value >= 0 else fallback

    resolved = resolve_window(settings, model_name)
    return ContextBudget(
        history_max=_int("agent.context.history_max", HISTORY_MAX),
        compress_budget=_int("agent.context.compress_budget", COMPRESS_BUDGET),
        window_tokens=resolved.window_tokens,
        max_output_tokens=resolved.max_output_tokens,
        auto_compact_at=_int("agent.context.auto_compact_at", 75),
        compact_target=_int("agent.context.compact_target", 0),
        memory_cards=_int_or_zero("agent.memory.context_cards", MEMORY_CARDS),
        memory_card_chars=_int_or_zero("agent.memory.context_card_chars", MEMORY_CARD_CHARS),
        recall_facts=_int_or_zero("agent.memory.recall_facts", RECALL_FACTS),
        recall_chars=_int_or_zero("agent.memory.recall_chars", RECALL_CHARS),
    )


__all__ = [
    "MEMORY_CARDS",
    "MEMORY_CARD_CHARS",
    "RECALL_CHARS",
    "RECALL_FACTS",
    "ContextBudget",
    "budget_from_settings",
]
