"""Context assembly: rules -> scoped rules -> persona -> profile -> recent
memory cards -> skill index -> task brief -> subagent digests -> pages.

Each layer is injected as a summary; full content is loaded on demand via
OnDemandLoader. The memory-card layer is bounded by its own budget
(count + characters) and, living in the system layer, is counted by the
context governor like every other layer. The skill / profile / task /
digest / page / MCP layers carry their own character caps (plus an entry
cap for the skill index); a zero cap omits the layer entirely.
"""

from __future__ import annotations

from typing import Any

from agent.context.budgets import (
    DIGEST_CHARS,
    MCP_CHARS,
    PAGE_CHARS,
    PROFILE_CHARS,
    SKILL_CHARS,
    SKILL_MAX,
    TASK_CHARS,
)
from agent.context.pages import PageContextRegistry
from agent.context.scoped_rules import ScopedRules
from agent.contracts import MemoryRecallSource, SkillIndexProvider, TaskSpec
from agent.personas import Persona

MEMORY_CARDS_HEADER = "【最近记忆】"
_CARD_FIELD_CHARS = 60


def render_memory_cards(memory: MemoryRecallSource, *, count: int, max_chars: int) -> str:
    """Compact lines for the most recent episodic entries, newest first,
    trimmed oldest-first to the character cap; "" when nothing fits."""
    if count <= 0 or max_chars <= 0:
        return ""
    lines: list[str] = []
    for entry in memory.episodic.recent(limit=count):
        detail = entry.get("detail") or {}
        action = detail.get("action") if isinstance(detail, dict) else None
        target = str(action.get("target") or "") if isinstance(action, dict) else ""
        result = str(detail.get("result") or "") if isinstance(detail, dict) else ""
        head = f"- [{entry.get('kind', '')}] {entry.get('summary', '')}"
        if target:
            head += f" {target[:_CARD_FIELD_CHARS]}"
        if result:
            head += f" → {result[:_CARD_FIELD_CHARS]}"
        lines.append(head)
    while lines and sum(len(line) + 1 for line in lines) > max_chars:
        lines.pop()  # the list is newest-first, so the oldest card goes first
    return "\n".join(lines)


def truncate_layer(text: str, max_chars: int, marker: str) -> str:
    """Bound one pre-rendered system layer to max_chars, appending marker
    when truncated. Deterministic: the head is kept so repeated renders of
    the same input stay byte-identical for the provider prefix cache."""
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + marker
    return text


class ContextBuilder:
    def __init__(
        self,
        *,
        rules: list[str] | None = None,
        memory: MemoryRecallSource | None = None,
        digests: Any = None,  # DigestStore (duck-typed as render() to avoid a circular import)
        pages: PageContextRegistry | None = None,
        skills: SkillIndexProvider | None = None,
        scoped_rules: ScopedRules | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._memory = memory
        self._digests = digests
        self._pages = pages
        self._skills = skills
        self._scoped_rules = scoped_rules

    def system(
        self,
        *,
        persona: Persona | None = None,
        task: TaskSpec | None = None,
        style: str = "",
        conduct: str = "",
        guideline: str = "",
        memory_cards: int = 0,
        memory_card_chars: int = 0,
        plan_section: str = "",
        recall_section: str = "",
        mcp_section: str = "",
        skill_max: int = SKILL_MAX,
        skill_chars: int = SKILL_CHARS,
        profile_chars: int = PROFILE_CHARS,
        task_chars: int = TASK_CHARS,
        digest_chars: int = DIGEST_CHARS,
        page_chars: int = PAGE_CHARS,
        mcp_chars: int = MCP_CHARS,
    ) -> str:
        layers: list[str] = []
        if self._rules:
            layers.append("【全局规则】\n" + "\n".join(f"- {r}" for r in self._rules))
        if self._scoped_rules is not None:
            scoped = self._scoped_rules.render()
            if scoped:
                layers.append(f"【目录规则 {self._scoped_rules.path.name}】\n" + scoped)
        if conduct.strip():
            layers.append("【用户准则】\n" + conduct.strip())
        if persona is not None:
            layers.append(
                f"【人格】{persona.display_name}({persona.style})\n{persona.system_prompt}"
            )
        if guideline.strip():
            layers.append("【人格准则】\n" + guideline.strip())
        if style:
            layers.append(f"【风格】{style}")
        if self._skills is not None and skill_max > 0 and skill_chars > 0:
            # Skill index stays resident: name + one-line description only, full text via
            # load_skill on demand; the layer is omitted entirely when empty or budgeted off.
            # Entry order follows the loader scan (sorted by path) so truncation is deterministic.
            entries = self._skills.index()
            if entries:
                total = len(entries)
                lines = [f"{e['name']}: {e['description']}" for e in entries[:skill_max]]
                if total > len(lines):
                    lines.append(
                        f"…(还有 {total - len(lines)} 个 skill 未显示，可调大 agent.context.skill_max)"
                    )
                block = (
                    "【可用 skill】\n"
                    + "\n".join(lines)
                    + "\n需要步骤时用 skill(action=load, name) 取全文。"
                )
                layers.append(truncate_layer(block, skill_chars, "\n…(skill 索引过长已截断)"))
        # Layer ordering serves the provider prefix cache: stable layers
        # (rules/persona/style/skills) come first, per-turn volatile layers
        # (profile/cards/task/digests/pages/plan) after them, so a turn-to-
        # turn change only invalidates the tail of the system prompt
        if self._memory is not None and profile_chars > 0:
            layers.append("【用户画像】\n" + self._memory.profile.render(max_chars=profile_chars))
            cards = render_memory_cards(
                self._memory, count=memory_cards, max_chars=memory_card_chars
            )
            if cards:
                layers.append(MEMORY_CARDS_HEADER + "\n" + cards)
        if task is not None and task.goal and task_chars > 0:
            block = f"【任务书】目标: {task.goal}"
            if task.constraints:
                block += f"\n约束: {task.constraints}"
            if task.done_when:
                block += f"\n完成判定: {task.done_when}"
            layers.append(truncate_layer(block, task_chars, "\n…(任务书过长已截断)"))
        if recall_section:
            # Resident relevance layer (memory read policy): memory hits for
            # the current input. Sits after the per-instance task layer and
            # before the more volatile digest/page layers - it re-renders per
            # turn with the input, so it belongs in the volatile tail.
            layers.append(recall_section)
        if self._digests is not None and digest_chars > 0:
            rendered = self._digests.render()
            if rendered:
                layers.append(
                    "【进行中的 subagent】\n"
                    + truncate_layer(rendered, digest_chars, "\n…(subagent 摘要过长已截断)")
                )
        if self._pages is not None and page_chars > 0:
            layers.append(
                "【用户当前页面】\n"
                + truncate_layer(self._pages.render(), page_chars, "…(页面信息过长已截断)")
            )
        if plan_section:
            # Volatile layer stays last: per-turn review-phase state must not
            # bust the prefix cache for the stable layers above
            layers.append(plan_section)
        if mcp_section and mcp_chars > 0:
            # Server-declared instructions (volatile tail: servers connect and
            # disconnect asynchronously, so this changes rarely but is not
            # stable); content is pre-rendered by the caller, sorted by sid
            layers.append(truncate_layer(mcp_section, mcp_chars, "\n…(MCP 指引过长已截断)"))
        return "\n\n".join(layers)

    def messages(self, system: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"role": "system", "content": system}, *history]


__all__ = ["MEMORY_CARDS_HEADER", "ContextBuilder", "render_memory_cards", "truncate_layer"]
