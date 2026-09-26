"""Shared blackboard: bounded per-task notes, concurrent-safe writes."""

from __future__ import annotations

import asyncio

from agent.orchestrator import blackboard as blackboard_module
from agent.orchestrator.blackboard import Blackboard


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


class TestReadShapes:
    def test_unknown_task_reads_empty(self) -> None:
        b = Blackboard()
        assert b.read(task="missing") == []

    def test_limit_clamped_into_range(self) -> None:
        b = Blackboard()
        for i in range(5):
            b.write(task="t", text=f"n{i}", author="a")
        assert len(b.read(task="t", limit=3)) == 3
        assert len(b.read(task="t", limit=999)) == 5  # capped at the card maximum
        assert len(b.read(task="t", limit=0)) == 1  # floor at one
        assert len(b.read(task="t", limit=-4)) == 1

    def test_global_read_interleaves_all_tasks_newest_first(self, monkeypatch) -> None:
        """Empty task: every task's cards merged, sorted by ts descending, each
        row stamped with its task."""
        clock = {"t": 1000.0}
        monkeypatch.setattr(blackboard_module.time, "time", lambda: clock["t"])
        b = Blackboard()
        b.write(task="t1", text="old t1", author="a")
        clock["t"] += 1
        b.write(task="t2", text="new t2", author="a")
        clock["t"] += 1
        b.write(task="t1", text="newest t1", author="a")
        merged = b.read(task="")
        assert [c["text"] for c in merged] == ["newest t1", "new t2", "old t1"]
        assert merged[0]["task"] == "t1" and merged[1]["task"] == "t2"


class TestClearAndBounds:
    def test_clear_one_task_and_all(self) -> None:
        b = Blackboard()
        b.write(task="t1", text="x", author="a")
        b.write(task="t1", text="y", author="a")
        b.write(task="t2", text="z", author="a")
        assert b.clear(task="t1") == 2
        assert b.read(task="t1") == []
        assert len(b.read(task="t2")) == 1
        assert b.clear() == 1  # remaining t2 card
        assert b.read(task="") == []

    def test_clear_unknown_task_counts_zero(self) -> None:
        b = Blackboard()
        assert b.clear(task="nope") == 0

    def test_long_text_and_author_truncated(self) -> None:
        b = Blackboard()
        b.write(task="t", text="x" * 900, author="a" * 200)
        (card,) = b.read(task="t")
        assert len(card["text"]) == 500
        assert len(card["author"]) == 80

    def test_long_task_name_truncated_to_80(self) -> None:
        b = Blackboard()
        out = b.write(task="t" * 120, text="x", author="a")
        assert out["task"] == "t" * 80
        assert b.read(task="t" * 80)

    def test_task_name_is_stripped_before_use(self) -> None:
        b = Blackboard()
        out = b.write(task="  t  ", text="ok", author="a")
        assert out["task"] == "t"
        assert b.read(task="t")

    def test_card_cap_evicts_oldest_within_task(self) -> None:
        b = Blackboard(max_cards=2)
        b.write(task="t", text="first", author="a")
        b.write(task="t", text="second", author="a")
        out = b.write(task="t", text="third", author="a")
        assert out["cards"] == 2
        assert [c["text"] for c in b.read(task="t")] == ["third", "second"]
