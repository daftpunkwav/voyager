"""Shared blackboard: bounded per-task notes, concurrent-safe writes."""

from __future__ import annotations

import asyncio

from agent.master.blackboard import Blackboard


class TestBlackboard:
    def test_write_read_roundtrip_newest_first(self) -> None:
        b = Blackboard()
        b.write(task="t", text="first", author="a1")
        b.write(task="t", text="second", author="a2")
        rows = b.read(task="t")
        assert rows[0]["text"] == "second" and rows[-1]["text"] == "first"
        assert rows[0]["author"] == "a2"

    def test_card_and_task_caps(self) -> None:
        b = Blackboard(max_cards=3, max_tasks=2)
        for i in range(5):
            b.write(task="t", text=f"n{i}", author="a")
        cards = b.read(task="t")
        assert len(cards) == 3 and [c["text"] for c in reversed(cards)] == ["n2", "n3", "n4"]
        b.write(task="t2", text="x", author="a")
        b.write(task="t3", text="y", author="a")  # evicts the oldest task board
        assert b.read(task="t") == []

    def test_empty_text_rejected(self) -> None:
        b = Blackboard()
        assert "error" in b.write(task="t", text="  ", author="a")
        assert "error" in b.write(task="", text="x", author="a")

    async def test_concurrent_writers_keep_all_cards(self) -> None:
        b = Blackboard(max_cards=50, max_tasks=5)

        async def writer(i: int) -> None:
            for j in range(10):
                b.write(task=f"t{i}", text=f"note {j}", author=f"a{i}")

        await asyncio.gather(*(writer(i) for i in range(5)))
        total = sum(len(b.read(task=f"t{i}", limit=50)) for i in range(5))
        assert total == 50  # no lost updates under the lock
