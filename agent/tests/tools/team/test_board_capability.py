"""The board capability (the task-scoped shared blackboard surface): default
task/author resolution through the executing instance context, explicit
human-supplied values, and the action validation ladder.

Test type: integration for the registry binding (built app) plus direct
board_action units for the contextvar-driven defaults.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agent.build import build_agent
from agent.capabilities.team.board import board_action
from agent.llm import FakeLLM
from agent.orchestrator.blackboard import Blackboard
from agent.runtime.current import current_instance
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError


class TestBoardActionDefaults:
    def test_without_instance_writes_need_an_explicit_task(self) -> None:
        """No executing instance and no explicit task: the write has no scope
        to land in and is rejected with a readable error (never a crash)."""
        blackboard = Blackboard()
        token = current_instance.set(None)
        try:
            out = board_action(blackboard, action="write", text="hello")
            assert "error" in out
            # an explicit task rescues the human path; default author is "chat"
            board_action(blackboard, action="write", text="hello", task="t1")
            read = board_action(blackboard, action="read", task="t1")
            assert isinstance(read, dict)
            (card,) = read["items"]
            assert card["author"] == "chat" and card["text"] == "hello"
        finally:
            current_instance.reset(token)

    def test_instance_goal_and_name_become_defaults(self) -> None:
        blackboard = Blackboard()
        inst = SimpleNamespace(task=SimpleNamespace(goal="build the treehouse" * 10), name="rex")
        token = current_instance.set(inst)
        try:
            board_action(blackboard, action="write", text="a note")
            # blackboard.read(task="") is the merged view; it stamps each card
            # with its task so the default scope is observable
            (card,) = blackboard.read(task="")
            assert card["author"] == "rex"
            assert card["task"] == inst.task.goal[:80]  # goal truncated to 80
        finally:
            current_instance.reset(token)

    def test_explicit_values_override_defaults(self) -> None:
        blackboard = Blackboard()
        inst = SimpleNamespace(task=SimpleNamespace(goal="g"), name="rex")
        token = current_instance.set(inst)
        try:
            board_action(blackboard, action="write", text="note", task="t1", author="jamie")
            read = board_action(blackboard, action="read", task="t1")
            assert isinstance(read, dict)
            (card,) = read["items"]
            assert card["author"] == "jamie"
            assert "rex" not in card["author"]
        finally:
            current_instance.reset(token)

    def test_empty_text_rejected(self) -> None:
        token = current_instance.set(None)
        try:
            with pytest.raises(ServiceError) as exc:
                board_action(Blackboard(), action="write", text="   ")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            current_instance.reset(token)

    def test_unknown_action_rejected(self) -> None:
        token = current_instance.set(None)
        try:
            with pytest.raises(ServiceError) as exc:
                board_action(Blackboard(), action="wipe")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            current_instance.reset(token)


class TestBoardCapabilityBinding:
    async def test_capability_round_trip_through_the_registry(self, tmp_path) -> None:
        """The registered capability shares one Blackboard instance with the
        master: a write through the registry is readable back through it."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            write = await execute(
                app.registry,
                "board",
                ActorContext(actor=LOCAL_USER),
                {"action": "write", "text": "from the human side", "task": "t1", "author": "user"},
            )
            assert write["task"] == "t1" and write["cards"] == 1
            read = await execute(
                app.registry,
                "board",
                ActorContext(actor=LOCAL_USER),
                {"action": "read", "task": "t1"},
            )
            assert read["items"][0]["text"] == "from the human side"
            # same store as the master's blackboard
            assert app.master.blackboard.read(task="t1")[0]["author"] == "user"
        finally:
            app.memory.close()
