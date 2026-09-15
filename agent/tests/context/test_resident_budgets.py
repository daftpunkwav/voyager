"""Tests for resident system-prompt layer budgets (Phase A).

Every always-resident layer (skill index, profile, task brief, digests,
pages, MCP instructions) carries its own count/character budget from
ContextBudget; a zero budget omits the layer. Truncation is deterministic
(head kept) so the provider prefix cache stays stable.
"""

from agent.context import ContextBuilder, PageContextRegistry
from agent.context.budgets import (
    DIGEST_CHARS,
    MCP_CHARS,
    PAGE_CHARS,
    PROFILE_CHARS,
    SKILL_CHARS,
    SKILL_MAX,
    TASK_CHARS,
    ContextBudget,
    budget_from_settings,
)
from agent.memory import Memory
from agent.subagent import TaskBook


class _Settings:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str) -> object:
        return self._values.get(key)


class _Skills:
    def __init__(self, count: int) -> None:
        self._entries = [
            {"name": f"skill-{i:03d}", "description": f"description {i}"} for i in range(count)
        ]

    def index(self) -> list[dict[str, str]]:
        return list(self._entries)


class _Digests:
    def __init__(self, text: str) -> None:
        self._text = text

    def render(self) -> str:
        return self._text


class TestResidentBudgetDefaults:
    def test_new_fields_match_top_constants(self) -> None:
        budget = budget_from_settings(_Settings())
        assert budget == ContextBudget()
        assert (budget.skill_max, budget.skill_chars) == (SKILL_MAX, SKILL_CHARS)
        assert budget.mcp_chars == MCP_CHARS
        assert budget.digest_chars == DIGEST_CHARS
        assert budget.profile_chars == PROFILE_CHARS
        assert budget.task_chars == TASK_CHARS
        assert budget.page_chars == PAGE_CHARS

    def test_explicit_zero_disables(self) -> None:
        budget = budget_from_settings(
            _Settings(
                {
                    "agent.context.skill_max": 0,
                    "agent.context.skill_chars": 0,
                    "agent.context.mcp_chars": 0,
                    "agent.context.digest_chars": 0,
                    "agent.memory.profile_chars": 0,
                    "agent.context.task_chars": 0,
                    "agent.context.page_chars": 0,
                }
            )
        )
        assert budget.skill_max == 0
        assert budget.skill_chars == 0
        assert budget.mcp_chars == 0
        assert budget.digest_chars == 0
        assert budget.profile_chars == 0
        assert budget.task_chars == 0
        assert budget.page_chars == 0

    def test_dirty_values_fall_back(self) -> None:
        budget = budget_from_settings(
            _Settings(
                {
                    "agent.context.skill_max": "nope",
                    "agent.context.skill_chars": -5,
                    "agent.context.mcp_chars": "nope",
                    "agent.context.digest_chars": -1,
                    "agent.memory.profile_chars": "nope",
                    "agent.context.task_chars": -2,
                    "agent.context.page_chars": "nope",
                }
            )
        )
        assert budget.skill_max == SKILL_MAX
        assert budget.skill_chars == SKILL_CHARS
        assert budget.mcp_chars == MCP_CHARS
        assert budget.digest_chars == DIGEST_CHARS
        assert budget.profile_chars == PROFILE_CHARS
        assert budget.task_chars == TASK_CHARS
        assert budget.page_chars == PAGE_CHARS


class TestSkillLayerBudget:
    def test_entry_count_capped_with_notice(self) -> None:
        builder = ContextBuilder(skills=_Skills(40))
        system = builder.system(skill_max=30, skill_chars=100_000)
        assert "skill-029" in system
        assert "skill-030" not in system
        assert "还有 10 个 skill 未显示" in system

    def test_char_budget_truncates_with_marker(self) -> None:
        builder = ContextBuilder(skills=_Skills(5))
        system = builder.system(skill_max=30, skill_chars=50)
        assert "skill 索引过长已截断" in system

    def test_zero_budget_omits_layer(self) -> None:
        builder = ContextBuilder(skills=_Skills(5))
        assert "【可用 skill】" not in builder.system(skill_max=0, skill_chars=100_000)
        assert "【可用 skill】" not in builder.system(skill_max=30, skill_chars=0)

    def test_empty_index_omits_layer(self) -> None:
        builder = ContextBuilder(skills=_Skills(0))
        assert "【可用 skill】" not in builder.system()


class TestOtherLayerBudgets:
    def test_digest_truncated_and_omitted(self) -> None:
        builder = ContextBuilder(digests=_Digests("x" * 5000))
        assert "subagent 摘要过长已截断" in builder.system(digest_chars=100)
        assert "【进行中的 subagent】" not in builder.system(digest_chars=0)
        assert "【进行中的 subagent】" not in ContextBuilder().system()

    def test_task_truncated_and_omitted(self) -> None:
        task = TaskBook(goal="g" * 3000, constraints="c", done_when="d")
        assert "任务书过长已截断" in ContextBuilder().system(task=task, task_chars=100)
        assert "【任务书】" not in ContextBuilder().system(task=task, task_chars=0)

    def test_page_truncated_and_omitted(self, tmp_path) -> None:
        pages = PageContextRegistry()
        pages.update("notes", "n" * 3000)
        assert "页面信息过长已截断" in ContextBuilder(pages=pages).system(page_chars=100)
        assert "【用户当前页面】" not in ContextBuilder(pages=pages).system(page_chars=0)

    def test_mcp_truncated_and_omitted(self) -> None:
        section = "【MCP: s】\n" + "y" * 3000
        assert "MCP 指引过长已截断" in ContextBuilder().system(mcp_section=section, mcp_chars=100)
        assert "【MCP" not in ContextBuilder().system(mcp_section=section, mcp_chars=0)

    def test_profile_capped_and_omitted(self, tmp_path) -> None:
        memory = Memory(tmp_path)
        try:
            memory.profile.set("language", "Chinese")
            full = ContextBuilder(memory=memory).system()
            assert "Chinese" in full
            assert "【用户画像】" not in ContextBuilder(memory=memory).system(profile_chars=0)
            capped = ContextBuilder(memory=memory).system(profile_chars=10)
            assert len(capped) < len(full)
        finally:
            memory.close()
