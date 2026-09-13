"""The shared context-management operations: ONE implementation that both
surfaces bind to under the same names.

The LLM tool (tools/meta/context_tools: context_status / compact_context) and
the human capability (capabilities/context: context_status / compact_context)
are thin transport bindings around these functions — the tool resolves the
executing instance via the current_instance ContextVar, the capability
resolves the addressed session and persists afterwards. Same name, same
engine, two drivers.

The instance parameter is duck-typed on purpose: a runtime import of
agent.subagent.instance here would create a cycle through agent.tools.__init__
(instance imports tools.core, whose package __init__ imports these tools).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.context.builder import MEMORY_CARDS_HEADER
from agent.context.tokenizer import estimate_text

if TYPE_CHECKING:
    from agent.subagent.instance import SubagentInstance


def _memory_cards_tokens(system: str) -> int:
    """Estimated tokens of the resident memory-card layer inside the system
    prompt (0 when the layer is absent)."""
    start = system.find(MEMORY_CARDS_HEADER)
    if start < 0:
        return 0
    end = system.find("\n\n【", start + len(MEMORY_CARDS_HEADER))
    block = system[start:] if end < 0 else system[start:end]
    return estimate_text(block)


def context_status(*, instance: SubagentInstance) -> dict[str, Any]:
    """Usage facts for one instance's live transcript (window, used, threshold)
    plus the share taken by the resident memory cards and the prefix-cache
    health the instance's sentinel has accumulated."""
    status = instance.governor().status(instance.context_view())
    # The system prompt is rebuilt per turn and kept on the instance, so the
    # card share is measurable between turns too (the view then holds only
    # the cross-turn history)
    status["memory_cards_tokens"] = _memory_cards_tokens(str(instance.system_prompt or ""))
    status["prefix_cache"] = instance.prefix_watch.health()
    return status


async def compact_context(*, instance: SubagentInstance) -> dict[str, Any] | None:
    """Restructure one instance's transcript via the LLM editor; None when
    already within target. Persisting is the caller's concern: the capability
    path persists the session afterwards, the tool path persists at turn end
    (mid-turn snapshots already carry the condensed transcript)."""
    return await instance.governor().compact(instance.context_view())


__all__ = ["compact_context", "context_status"]
