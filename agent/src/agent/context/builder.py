"""Context assembly: rules -> scoped rules -> persona -> profile -> recent
memory cards -> skill index -> task brief -> subagent digests -> pages.

Each layer is injected as a summary; full content is loaded on demand via
OnDemandLoader. The memory-card layer is bounded by its own budget
(count + characters) and, living in the system layer, is counted by the
context governor like every other layer.
"""

from __future__ import annotations

from typing import Any

from agent.context.pages import PageContextRegistry
from agent.context.scoped_rules import ScopedRules
from agent.contracts import SkillIndexProvider, TaskSpec
from agent.memory import Memory
from agent.personas import Persona

MEMORY_CARDS_HEADER = "【最近记忆】"
_CARD_FIELD_CHARS = 60


def render_memory_cards(memory: Memory, *, count: int, max_chars: int) -> str:
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


class ContextBuilder:
    def __init__(
        self,
        *,
        rules: list[str] | None = None,
        memory: Memory | None = None,
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
        if self._skills is not None:
            # Skill index stays resident: name + one-line description only, full text via
            # load_skill on demand; the layer is omitted entirely when empty
            entries = self._skills.index()
            if entries:
                layers.append(
                    "【可用 skill】\n"
                    + "\n".join(f"{e['name']}: {e['description']}" for e in entries)
                    + "\n需要步骤时用 load_skill(name) 取全文。"
                )
        # Layer ordering serves the provider prefix cache: stable layers
        # (rules/persona/style/skills) come first, per-turn volatile layers
        # (profile/cards/task/digests/pages/plan) after them, so a turn-to-
        # turn change only invalidates the tail of the system prompt
        if self._memory is not None:
            layers.append("【用户画像】\n" + self._memory.profile.render())
            cards = render_memory_cards(
                self._memory, count=memory_cards, max_chars=memory_card_chars
            )
            if cards:
                layers.append(MEMORY_CARDS_HEADER + "\n" + cards)
        if task is not None and task.goal:
            block = f"【任务书】目标: {task.goal}"
            if task.constraints:
                block += f"\n约束: {task.constraints}"
            if task.done_when:
                block += f"\n完成判定: {task.done_when}"
            layers.append(block)
        if recall_section:
            # Resident relevance layer (memory read policy): memory hits for
            # the current input. Sits after the per-instance task layer and
            # before the more volatile digest/page layers - it re-renders per
            # turn with the input, so it belongs in the volatile tail.
            layers.append(recall_section)
        if self._digests is not None:
            rendered = self._digests.render()
            if rendered:
                layers.append("【进行中的 subagent】\n" + rendered)
        if self._pages is not None:
            layers.append("【用户当前页面】\n" + self._pages.render())
        if plan_section:
            # Volatile layer stays last: per-turn review-phase state must not
            # bust the prefix cache for the stable layers above
            layers.append(plan_section)
        return "\n\n".join(layers)

    def messages(self, system: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"role": "system", "content": system}, *history]


__all__ = ["MEMORY_CARDS_HEADER", "ContextBuilder", "render_memory_cards"]
