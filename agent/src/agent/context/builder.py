"""Context assembly, split by cache stability:

- ContextBuilder.system(): the stable head — rules, scoped rules, conduct,
  persona, guideline, style, skill index, profile, task brief, MCP
  instructions. Byte-stable across turns unless a real source (settings,
  skills on disk, distillation) changed.
- ContextBuilder.turn_context(): the per-turn volatile block — recent memory
  cards, relevance recall, subagent digests, current page, plan gate. The
  caller (engine.turn) renders it into ONE trailing user-role row appended
  after the full history, so the request prefix (system + history) stays
  byte-identical across turns and the provider prefix cache survives: any
  per-turn change inside the system message would re-bill the whole history,
  because a provider cache is a byte-prefix of the entire request.

Each layer is injected as a summary; full content is loaded on demand via
OnDemandLoader. Layers carry their own character caps (plus an entry cap for
the skill index); a zero cap omits the layer entirely.
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
#: Marker prefixing the trailing per-turn context row (engine.turn); consumers
#: (react's idle-continue check, turn's history write-back) use it to tell the
#: volatile context row apart from real user input.
TURN_CONTEXT_HEADER = "【会话状态】"
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
        mcp_section: str = "",
        skill_max: int = SKILL_MAX,
        skill_chars: int = SKILL_CHARS,
        profile_chars: int = PROFILE_CHARS,
        task_chars: int = TASK_CHARS,
        mcp_chars: int = MCP_CHARS,
    ) -> str:
        """The stable head of the request. Only layers whose source changes
        rarely (settings, skills on disk, distillation, MCP mounts) live here:
        the profile rides along because distillation cadence is low, while the
        per-turn volatile layers are rendered by turn_context() instead."""
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
        if self._memory is not None and profile_chars > 0:
            layers.append("【用户画像】\n" + self._memory.profile.render(max_chars=profile_chars))
        if task is not None and task.goal and task_chars > 0:
            block = f"【任务书】目标: {task.goal}"
            if task.constraints:
                block += f"\n约束: {task.constraints}"
            if task.done_when:
                block += f"\n完成判定: {task.done_when}"
            layers.append(truncate_layer(block, task_chars, "\n…(任务书过长已截断)"))
        if mcp_section and mcp_chars > 0:
            # Server-declared instructions; changes only when servers mount or
            # unmount (rare), so unlike the per-turn layers it stays in the head.
            # Content is pre-rendered by the caller, sorted by sid.
            layers.append(truncate_layer(mcp_section, mcp_chars, "\n…(MCP 指引过长已截断)"))
        return "\n\n".join(layers)

    def turn_context(
        self,
        *,
        memory_cards: int = 0,
        memory_card_chars: int = 0,
        plan_section: str = "",
        recall_section: str = "",
        digest_chars: int = DIGEST_CHARS,
        page_chars: int = PAGE_CHARS,
    ) -> str:
        """The per-turn volatile block, rendered into one trailing user-role
        row by the caller. Returns "" when no layer has content, in which case
        no context row is appended at all.

        Layer order inside the block follows attention value: recent memory
        and relevance hits carry the most per-turn signal and come first;
        digests, the current page and the plan gate follow.
        """
        layers: list[str] = []
        if self._memory is not None and memory_card_chars > 0:
            cards = render_memory_cards(
                self._memory, count=memory_cards, max_chars=memory_card_chars
            )
            if cards:
                layers.append(MEMORY_CARDS_HEADER + "\n" + cards)
        if recall_section:
            # Resident relevance layer (memory read policy): memory hits for
            # the current input, so long-term knowledge surfaces without the
            # model having to call the recall tool.
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
            layers.append(plan_section)
        return "\n\n".join(layers)

    def messages(self, system: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"role": "system", "content": system}, *history]


__all__ = [
    "MEMORY_CARDS_HEADER",
    "TURN_CONTEXT_HEADER",
    "ContextBuilder",
    "render_memory_cards",
    "truncate_layer",
]
