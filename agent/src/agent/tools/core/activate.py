"""Graded tool activation for conversational instances (activate_tools).

A conversational instance (tool_allow=None) can call any registered tool via `call()`,
but `llm.complete` only receives the full schema of **activated** tools each
round — avoids stuffing ~a hundred bridge tool schemas into the model (root
cause of a 60s first-round read timeout). Conventions:

- Always active (CORE): orchestration-critical built-ins + this tool;
- `activate_tools(domain=...)` / `(names=[...])` merges matching tools into
  **that instance's** activation set (visible from the next complete call),
  without touching the shared global Toolbelt;
- Dispatched task subagents use trimmed() and already have few tools, so
  their full specs are given to the model and activation does not apply.

Activatable domains are not module constants: they are computed from the
`__` prefixes in the current Toolbelt roster (`domain_prefixes`), so newly
mounted `office__*` tools need no change here. The page pre-activation list
(`page_preactivate`) also lives here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent.tools.core.base import AgentTool, Toolbelt

#: Always active (full schema): tools that conversation orchestration cannot
#: do without, plus activate_tools itself; todowrite is the structured plan
#: for long/multi-step conversations (baseline 2026-09): small and
#: cross-domain, so kept always active
CORE_TOOLS = (
    "ask_user",
    "spawn_subagent",
    "skill",
    "memory",
    "request_context",
    "todowrite",
    # The workspace working set (read/write/edit/glob/grep/bash are
    # resident): without write and bash the model cannot do actual workspace
    # work and degrades into ask_user loops
    "read",
    "write",
    "edit",
    "bash",
    "grep",
    "glob",
    "settings__get_theme",
    "settings__set_theme",
    "activate_tools",
    # LLM-driven context management: the model reads its own window usage and
    # compacts proactively (the harness auto-triggers at the threshold too)
    "context",
    # Agent-side session surface: one aggregated tool (list/create/fork/…);
    # activation granularity is the whole surface (known cost, design §9.3)
    "session",
    # Usage self-awareness: the llm domain's usage stats are preactivated so
    # the model can check its own consumption without an activation round
    "llm__get_usage_stats",
)

#: Page -> pre-activated domain: when the user sits on one of these domain
#: pages, its tools merge in at conversation start, saving one activate_tools
#: round; other pages (settings/usage...) do not pre-activate. The list is
#: deliberately limited to three pages: generalizing "page id == domain name
#: means pre-activate" would dump the whole settings__* domain schema into the
#: conversation as soon as the settings page reports.
_PAGE_PREACTIVATE: dict[str, str] = {
    "notes": "notes",
    "graph": "graph",
    "sources": "sources",
}


def page_preactivate(page: str) -> str | None:
    """Tool domain matching the current page; None when unmapped (unit-tested directly)."""
    return _PAGE_PREACTIVATE.get(page)


def domain_prefixes(names: Iterable[str]) -> tuple[str, ...]:
    """Map `foo__bar` entries in the roster to foo (text before the first `__`).
    Built-ins without `__` (read / bash / activate_tools...) yield no domain. Deduplicated and sorted for a stable order.
    """
    prefixes = set()
    for n in names:
        head, sep, _tail = n.partition("__")
        if sep and head:
            prefixes.add(head)
    return tuple(sorted(prefixes))


# Guess domains to pre-activate from recent conversation (e.g. "test them all"
# carries no domain name; hints above such as notes/graph keywords supply it)
_DOMAIN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("notes", ("笔记", "底纹", "加粗", "回收站", "正文", "markdown")),
    ("graph", ("图谱", "索引", "节点", "建图")),
    ("sources", ("仓库", "导入", "github", "资源库", "剪藏")),
)


def infer_domains(*texts: str) -> tuple[str, ...]:
    """Guess domains from recent conversation; matched domains merge into the
    activation set at startup, saving one pure activate round."""
    blob = " ".join(texts).lower()
    found: list[str] = []
    for domain, hints in _DOMAIN_HINTS:
        if any(h.lower() in blob for h in hints):
            found.append(domain)
    return tuple(found)


def _activate_schema(domains: tuple[str, ...]) -> dict[str, Any]:
    """Parameter schema for activate_tools: the domain enum is computed from the current roster."""
    return {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": list(domains),
                "description": "按域激活:该域全部工具并入激活集(如 notes → notes__*)",
            },
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "按精确名激活(当前名册中存在的工具)",
            },
        },
    }


def _activate_handler(toolbelt: Toolbelt, active: set[str], domains: tuple[str, ...]):
    async def activate(domain: str | None = None, names: list[str] | None = None) -> str:
        """Merge matching tools into this instance's activation set; the LLM
        sees their full schema from the next round on."""
        pool = set(toolbelt.names())
        matched: set[str] = set()
        if domain:
            prefix = f"{domain}__"
            matched.update(n for n in pool if n.startswith(prefix))
        if names:
            matched.update(n for n in pool if n in set(names))
        if not matched:
            return (
                f"[无匹配] 当前名册中没有匹配的工具;可用域:{', '.join(domains)} 或用 names 给精确名"
            )
        active.update(matched)
        return f"已激活 {len(matched)} 个工具: {', '.join(sorted(matched))}"

    return activate


def graded_toolbelt(
    toolbelt: Toolbelt,
    active: set[str] | None = None,
    *,
    preactivate: tuple[str, ...] = (),
) -> Toolbelt:
    """Graded view for a conversational instance: the activation set defaults
    to CORE; cross-turn persistence requires the caller to hold the same set.

    preactivate: domains merged in immediately (e.g. pre-activate notes when
    the user is on the notes page, saving one activation round). activate_tools
    binds to the shared `active` reference, so the next specs() call reflects it.
    """
    if active is None:
        active = set(CORE_TOOLS)
    else:
        active.update(CORE_TOOLS)
    pool = set(toolbelt.names())
    for domain in preactivate:
        active.update(n for n in pool if n.startswith(f"{domain}__"))
    domains = domain_prefixes(pool)
    activate = AgentTool(
        name="activate_tools",
        description=(
            "按域或按名激活工具(domain=notes/sources/graph/… 或 names=[...]),"
            "激活后下一轮即可使用该工具;调用工具前若怀疑其未激活,先激活再调"
        ),
        handler=_activate_handler(toolbelt, active, domains),
        schema=_activate_schema(domains),
    )
    return toolbelt.with_active(active, extra={"activate_tools": activate})
