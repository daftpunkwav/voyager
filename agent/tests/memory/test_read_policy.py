"""Memory read policy: the resident relevance layer. Selection through the
recall facade, episodic de-duplication against the resident cards, bounding,
content-addressed rendering, and the end-to-end wiring into the per-turn
system prompt."""

from __future__ import annotations

import asyncio

from agent.build import build_agent
from agent.llm import FakeLLM
from agent.memory.read_policy import HEADER, render_relevant_recall


def _memory(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    return app, app.memory


def test_empty_query_or_budget_renders_nothing(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.semantic.add("postgres", "端口", "5432")
        assert render_relevant_recall(memory, "   ") == ""
        assert render_relevant_recall(memory, "postgres", limit=0) == ""
        assert render_relevant_recall(memory, "postgres", max_chars=0) == ""
    finally:
        app.close()


def test_semantic_fact_renders_as_fact_line(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.semantic.add("postgres", "端口", "5432")
        out = render_relevant_recall(memory, "postgres 端口是多少")
        assert HEADER in out
        assert "[事实] postgres 端口 5432" in out
    finally:
        app.close()


def test_profile_hit_renders_with_label(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.profile.set("部署约束", "纯本地单用户,永不上线")
        # recall is lexical on whitespace-split terms: the query carries the
        # profile key's tokens as separate words
        out = render_relevant_recall(memory, "部署 约束")
        assert "[画像] 部署约束: 纯本地单用户,永不上线" in out
    finally:
        app.close()


def test_profile_hit_excluded_when_key_on_resident_layer(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.profile.set("部署约束", "纯本地单用户,永不上线")
        excluded = render_relevant_recall(memory, "部署 约束", exclude_profile_keys={"部署约束"})
        assert "[画像]" not in excluded
        kept = render_relevant_recall(memory, "部署 约束", exclude_profile_keys={"别的键"})
        assert "[画像] 部署约束" in kept
    finally:
        app.close()


def test_episodic_hit_and_card_exclusion(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.episodic.log("tool", "用 todo_write 建了周报待办")
        exclude = {"用 todo_write 建了周报待办"}
        kept = render_relevant_recall(memory, "周报", exclude_summaries=exclude)
        assert kept == ""  # the only hit is already on a resident card
        shown = render_relevant_recall(memory, "周报")
        assert "[tool] 用 todo_write 建了周报待办" in shown
    finally:
        app.close()


def test_layer_is_bounded_to_max_chars(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        for i in range(6):
            memory.semantic.add(f"主题{i}", "细节", "很长的内容" * 20)
        out = render_relevant_recall(memory, "主题", limit=6, max_chars=200)
        body = out.removeprefix(HEADER + "\n")
        assert len(body) <= 200
        assert out.count("[事实]") < 6  # tail hits were dropped, not overflowing
    finally:
        app.close()


def test_rendering_is_content_addressed(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:
        memory.semantic.add("redis", "密码", "secret-x")
        a = render_relevant_recall(memory, "redis 密码")
        b = render_relevant_recall(memory, "redis 密码")
        assert a == b  # identical bytes keep the provider prefix stable
    finally:
        app.close()


def test_broken_store_never_breaks_the_turn(tmp_path) -> None:
    app, memory = _memory(tmp_path)
    try:

        def _boom(*a, **kw):
            raise RuntimeError("store gone")

        memory.recall = _boom  # type: ignore[method-assign]
        assert render_relevant_recall(memory, "anything") == ""
    finally:
        app.close()


def test_turn_system_prompt_carries_relevance_layer(tmp_path) -> None:
    """End-to-end: a seeded fact surfaces in the next turn's system prompt
    without the model calling recall_memory."""
    llm = FakeLLM()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        app.memory.semantic.add(" vacation", "政策", "年假五天,需提前一周审批")

        async def _drive() -> None:
            await app.master.handle_user_message("公司的 vacation 政策是怎样的?")
            while app.master._bg:
                await asyncio.gather(*list(app.master._bg))

        asyncio.run(_drive())
        sent = llm.calls[0]["messages"]
        system = str(sent[0].get("content") or "")
        assert HEADER in system
        assert "年假五天" in system
    finally:
        app.memory.close()


def test_turn_system_prompt_skips_duplicate_profile_line(tmp_path) -> None:
    """End-to-end: a profile key already on the resident profile layer is not
    repeated as a [画像] line in the relevance layer."""
    llm = FakeLLM()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        app.memory.profile.set("部署约束", "纯本地单用户,永不上线")

        async def _drive() -> None:
            await app.master.handle_user_message("部署 约束是什么?")
            while app.master._bg:
                await asyncio.gather(*list(app.master._bg))

        asyncio.run(_drive())
        sent = llm.calls[0]["messages"]
        system = str(sent[0].get("content") or "")
        assert "【用户画像】" in system
        assert "部署约束" in system
        assert "[画像] 部署约束" not in system
    finally:
        app.memory.close()


def test_aged_hits_carry_freshness_suffix_and_stale_note(tmp_path) -> None:
    """Hits older than a day render "(N天前)" and the staleness caveat; fresh
    hits stay clean (content-addressed rendering keeps prefix cache stable)."""
    app, memory = _memory(tmp_path)
    try:
        memory.semantic.add("redis", "密码", "secret-x")
        # Backdate the fact beyond the freshness boundary by rewriting ts
        with memory.semantic._conn as conn:  # noqa: SLF001  # test backdoor
            conn.execute("UPDATE facts SET ts = ts - 86400 * 30")
        out = render_relevant_recall(memory, "redis 密码")
        assert "(30天前)" in out
        assert "以当前实际状态为准" in out
        # Fresh rendering carries neither the suffix nor the caveat
        memory.semantic.add("vacation", "政策", "年假五天")
        fresh = render_relevant_recall(memory, "vacation 政策")
        assert "天前" not in fresh
        assert "以当前实际状态为准" not in fresh
    finally:
        app.close()
