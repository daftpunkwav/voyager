"""Tests for asking the user: question events, answer delivery, timeout
fallback, and the chat closed loop.
"""

import asyncio

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.tools.interact.question_broker import AGENT_ASK, AskUser, Question
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, DomainEvent
from platform_eventbus import EventBus, EventLog


async def test_question_event_and_answer(tmp_path) -> None:
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    asker = AskUser(bus)
    q = Question(prompt="选哪个?", kind="choice", options=("A", "B"))
    task = asyncio.create_task(asker.ask(q))
    events: list = []
    for _ in range(50):  # publish persists via to_thread; polling avoids a fixed short-sleep race
        events = log.read_after(types=[AGENT_ASK])
        if events:
            break
        await asyncio.sleep(0.01)
    assert asker.pending_count == 1
    assert len(events) == 1
    payload = events[0][1].payload
    assert payload["prompt"] == "选哪个?" and payload["options"] == ["A", "B"]
    assert asker.answer(payload["question_id"], "B") is True
    assert await task == "B"
    assert asker.pending_count == 0


async def test_timeout_returns_none(tmp_path) -> None:
    asker = AskUser(None)  # works without a bus too (no event emitted, just waits)
    result = await asker.ask(Question(prompt="在吗?", timeout_s=0.02))
    assert result is None


async def test_answer_unknown_id_misses(tmp_path) -> None:
    asker = AskUser(None)
    assert asker.answer("ghost", 1) is False


async def test_tool_coerces_object_options_to_strings(tmp_path) -> None:
    """The LLM sometimes sends choice options as objects like {"content": "..."}:
    the tool must normalize them to strings, or the UI crashes rendering the
    payload as React children (2026-09-08 chat page crash)."""
    llm = FakeLLM(
        [
            LLMReply(
                tool_calls=(
                    ToolCall(
                        "t1",
                        "ask_user",
                        {
                            "prompt": "按什么结构写?",
                            "kind": "choice",
                            "options": [
                                {"content": "三件套"},
                                {"label": "自由发挥"},
                                "纯字符串",
                            ],
                        },
                    ),
                )
            ),
            LLMReply(text="好的。"),
        ]
    )
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    run_task = asyncio.create_task(app.master.handle_user_message("写游戏笔记"))
    payload = None
    for _ in range(200):
        events = app.log.read_after(types=[AGENT_ASK])
        if events:
            payload = events[0][1].payload
            break
        await asyncio.sleep(0.01)
    assert payload is not None
    assert payload["options"] == ["三件套", "自由发挥", "纯字符串"]
    out = await execute(
        app.registry,
        "answer_question",
        ActorContext(actor=LOCAL_USER),
        {"question_id": payload["question_id"], "value": "三件套"},
    )
    assert out["matched"] is True
    await asyncio.wait_for(run_task, timeout=5)
    app.memory.close()


class TestChatLoopClosedLoop:
    async def test_askuser_via_chat_then_answer_continues(self, tmp_path, settle) -> None:
        """Chat closed loop: the chat instance calls ask_user -> the frontend answers via the same answer_question path -> the agent continues.

        FakeLLM script: round 1 emits a choice question tool call; after the user answers,
        round 2 produces the final reply.
        """
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall(
                            "t1",
                            "ask_user",
                            {"prompt": "选哪个方案?", "kind": "choice", "options": ["A", "B"]},
                        ),
                    )
                ),
                LLMReply(text="已按你的选择继续。"),
            ]
        )
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
        run_task = asyncio.create_task(app.master.handle_user_message("帮我选方案"))
        payload = None
        for _ in range(
            200
        ):  # wait for the agent.ask event to land (publish goes through to_thread)
            events = app.log.read_after(types=[AGENT_ASK])
            if events:
                payload = events[0][1].payload
                break
            await asyncio.sleep(0.01)
        assert payload is not None, "agent.ask 未发布"
        assert payload["kind"] == "choice" and payload["options"] == ["A", "B"]

        # The same answer path as the frontend AskDialog (the agent.answer_question capability)
        out = await execute(
            app.registry,
            "answer_question",
            ActorContext(actor=LOCAL_USER),
            {"question_id": payload["question_id"], "value": "B"},
        )
        assert out["matched"] is True

        await asyncio.wait_for(
            run_task, timeout=5
        )  # the entry returns immediately (turns run in the background)

        await settle(
            app
        )  # wait for the background turn to consume the answer and produce the final reply
        replies = [
            e.payload["content"] for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
        ]
        assert "已按你的选择继续。" in replies  # the agent continues after the answer and replies
        app.memory.close()


async def test_tool_schema_offers_free_answer_forms(tmp_path) -> None:
    """The model decides the answer form freely: multi_choice joins the enum,
    options carry no length cap, and the description tells the model the user
    can always answer with free text."""
    from agent.main import build_agent as _build

    app = _build(data_dir=tmp_path / "rd2", workspace_dir=tmp_path / "ws2", llm=FakeLLM())
    try:
        specs = {s.name: s for s in app.spawner._toolbelt.specs()}
        kind_enum = specs["ask_user"].schema["properties"]["kind"]["enum"]
        assert "multi_choice" in kind_enum and "slider" in kind_enum
        options_schema = specs["ask_user"].schema["properties"]["options"]
        assert "maxItems" not in options_schema
        assert "自由" in specs["ask_user"].description or "任意" in specs["ask_user"].description
    finally:
        app.close()
        app.memory.close()


async def test_multi_choice_answer_is_a_list(tmp_path) -> None:
    """multi_choice answers arrive as a list of picked strings (frontend toggles
    submit an array); the tool hands the raw list to the model."""
    log = EventLog(tmp_path / "ev3.db")
    bus = EventBus(log)
    asker = AskUser(bus)
    q = Question(prompt="要哪些?", kind="multi_choice", options=("A", "B", "C"))
    task = asyncio.create_task(asker.ask(q))
    payload = None
    for _ in range(50):
        events = log.read_after(types=[AGENT_ASK])
        if events:
            payload = events[0][1].payload
            break
        await asyncio.sleep(0.01)
    assert payload is not None and payload["kind"] == "multi_choice"
    assert asker.answer(payload["question_id"], ["A", "自定义"]) is True
    assert await task == ["A", "自定义"]


def test_repl_multi_choice_coercion() -> None:
    """REPL free-text answers for multi_choice split on separators; indexes map
    to preset options, unknown tokens pass through as custom answers."""
    from agent.repl import _coerce_answer

    out = _coerce_answer("multi_choice", ("海边", "山里", "城市"), "1、3、自定义项")
    assert out == ["海边", "城市", "自定义项"]
    # Plain spaces stay inside one token: a custom answer may contain them
    assert _coerce_answer("multi_choice", (), "三件套 A 版") == ["三件套 A 版"]
    assert _coerce_answer("multi_choice", ("甲",), "甲,再来一份") == ["甲", "再来一份"]


async def test_option_count_bounds_and_rating_kind(tmp_path) -> None:
    """Per-kind option-count bounds are enforced with model-actionable errors
    (no dialog flashes on a bad call); slider takes 1-8 tick labels; rating
    takes no options and answers as an integer."""
    app = build_agent(data_dir=tmp_path / "rd3", workspace_dir=tmp_path / "ws3", llm=FakeLLM())
    try:
        from agent.tools.interact.ask_user import ask_user_tool

        tool = ask_user_tool(app.asker)
        # Invalid counts: rejected synchronously with a model-actionable text,
        # and no question is published
        too_few = await tool.handler(prompt="选", kind="choice", options=["只有一个"])
        too_many = await tool.handler(
            prompt="选", kind="choice", options=[str(i) for i in range(9)]
        )
        assert "参数错误" in too_few and "2-8" in too_few
        assert "2-8" in too_many
        assert "2-8" in await tool.handler(prompt="选", kind="multi_choice", options=["a"])
        assert "1-8" in await tool.handler(prompt="评", kind="slider", options=[])
        assert app.asker.pending_count == 0

        # Valid slider: the question publishes; the labeled label comes back
        task = asyncio.create_task(tool.handler(prompt="评", kind="slider", options=["低", "高"]))
        for _ in range(100):
            if app.asker.pending_count:
                break
            await asyncio.sleep(0.01)
        qid = next(iter(app.asker._pending))
        assert app.asker.answer(qid, "高") is True
        assert await asyncio.wait_for(task, timeout=5) == "高"

        # Rating: no options; the answer rides through as an int
        task = asyncio.create_task(tool.handler(prompt="打分", kind="rating"))
        for _ in range(100):
            if app.asker.pending_count:
                break
            await asyncio.sleep(0.01)
        qid = next(iter(app.asker._pending))
        assert app.asker.answer(qid, 4) is True
        assert await asyncio.wait_for(task, timeout=5) == 4
    finally:
        app.close()
        app.memory.close()


def test_repl_rating_coercion() -> None:
    """REPL rating input clamps to 1-5; non-numeric passes through as text."""
    from agent.repl import _coerce_answer

    assert _coerce_answer("rating", (), "4") == 4
    assert _coerce_answer("rating", (), "99") == 5
    assert _coerce_answer("rating", (), "还行吧") == "还行吧"


async def test_duplicate_options_dedup_before_bounds(tmp_path) -> None:
    """Duplicate labels collapse in order before the count check (a repeated
    option would collide as a React key and double-count the bounds)."""
    from agent.tools.interact.ask_user import ask_user_tool

    log = EventLog(tmp_path / "ev4.db")
    bus = EventBus(log)
    asker = AskUser(bus)
    tool = ask_user_tool(asker)
    task = asyncio.create_task(
        tool.handler(prompt="选", kind="choice", options=["A", "B", "A", "B", "A"])
    )
    payload = None
    for _ in range(50):
        events = log.read_after(types=[AGENT_ASK])
        if events:
            payload = events[0][1].payload
            break
        await asyncio.sleep(0.01)
    # 5 raw entries dedup to 2 unique -> inside the 2-8 bounds and published
    assert payload is not None and payload["options"] == ["A", "B"]
    assert asker.answer(payload["question_id"], "A") is True
    assert await asyncio.wait_for(task, timeout=5) == "A"


def test_repl_rating_extreme_inputs_do_not_crash() -> None:
    from agent.repl import _coerce_answer

    assert _coerce_answer("rating", (), "inf") == "inf"  # OverflowError path
    assert _coerce_answer("rating", (), "nan") == "nan"
    assert _coerce_answer("rating", (), "0") == 1


async def test_question_event_carries_session(tmp_path) -> None:
    """agent.ask is stamped with the executing turn's chat session so a
    multi-session frontend routes the dialog to the asking lane; session-less
    execution (REPL, background) publishes an empty session."""
    from types import SimpleNamespace

    from agent.runtime.current import current_instance

    log = EventLog(tmp_path / "ev-session.db")
    bus = EventBus(log)
    asker = AskUser(bus)

    task = asyncio.create_task(asker.ask(Question(prompt="会话内?")))
    payload = None
    for _ in range(50):
        events = log.read_after(types=[AGENT_ASK])
        if events:
            payload = events[0][1].payload
            break
        await asyncio.sleep(0.01)
    assert payload is not None and payload["session"] == ""
    asker.answer(payload["question_id"], "ok")
    await asyncio.wait_for(task, timeout=5)
    first_qid = payload["question_id"]

    token = current_instance.set(SimpleNamespace(task=SimpleNamespace(session="sess-a")))
    try:
        task = asyncio.create_task(asker.ask(Question(prompt="会话内?")))
        payload = None
        for _ in range(50):
            events = log.read_after(types=[AGENT_ASK])
            # The log replays older asks: accept only the new question's event
            fresh = [e for e in events if e[1].payload["question_id"] != first_qid]
            if fresh:
                payload = fresh[0][1].payload
                break
            await asyncio.sleep(0.01)
        assert payload is not None and payload["session"] == "sess-a"
        asker.answer(payload["question_id"], "ok")
        await asyncio.wait_for(task, timeout=5)
    finally:
        current_instance.reset(token)
