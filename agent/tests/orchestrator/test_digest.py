"""Digest store: the master's per-subagent status cards — upsert lifecycle,
terminal-card trimming under the cap (active and fresh cards survive), and
the render format the master prompt embeds.

Test type: unit (duck-typed instances, no spawner assembly).
"""

from __future__ import annotations

from types import SimpleNamespace

from agent.orchestrator import digest as digest_module
from agent.orchestrator.digest import DigestStore


def _inst(
    id: str,
    name: str = "worker",
    goal: str = "ship it",
    status: str = "running",
    step: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        task=SimpleNamespace(goal=goal),
        status=SimpleNamespace(value=status),
        last_step_summary=lambda step=step: step,
    )


class TestCardLifecycle:
    def test_upsert_creates_then_updates_in_place(self) -> None:
        store = DigestStore()
        card = store.upsert(_inst("i1", name="scout", status="running"))
        assert card.subagent_id == "i1" and card.status == "running"
        card2 = store.upsert(_inst("i1", name="scout", status="completed"))
        assert card2.status == "completed"
        assert len(store.list()) == 1  # one card per subagent id
        assert store.list()[0].status == "completed"

    def test_step_summary_truncated_to_cap(self) -> None:
        store = DigestStore()
        card = store.upsert(_inst("i1", step="s" * 300))
        assert len(card.last_step) == store.STEP_MAX

    def test_remove_drops_the_card(self) -> None:
        store = DigestStore()
        store.upsert(_inst("i1"))
        store.remove("i1")
        assert store.list() == []
        store.remove("i1")  # idempotent

    def test_list_newest_first(self, monkeypatch) -> None:
        clock = {"t": 1000.0}
        monkeypatch.setattr(digest_module.time, "time", lambda: clock["t"])
        store = DigestStore()
        for i in ("i1", "i2", "i3"):
            clock["t"] += 1.0
            store.upsert(_inst(i))
        assert [c.subagent_id for c in store.list()] == ["i3", "i2", "i1"]


class TestRender:
    def test_empty_store_renders_empty_string(self) -> None:
        assert DigestStore().render() == ""

    def test_render_format_with_and_without_recent_step(self, monkeypatch) -> None:
        # Card order is newest-first by ts: advance the clock so the two
        # upserts cannot land on the same timestamp (render order flips on ties).
        clock = {"t": 1000.0}
        monkeypatch.setattr(digest_module.time, "time", lambda: clock["t"])
        store = DigestStore()
        clock["t"] += 1.0
        store.upsert(_inst("i1", name="scout", status="running", step="reading files"))
        clock["t"] += 1.0
        store.upsert(_inst("i2", name="planner", status="pending", step=""))
        text = store.render()
        lines = text.splitlines()
        # render follows list(): newest card first
        assert lines[0] == "- [pending] planner(i2): ship it"  # no empty tail
        assert lines[1] == "- [running] scout(i1): ship it | recent: reading files"


class TestTerminalTrimming:
    def test_over_cap_oldest_terminal_cards_evicted(self, monkeypatch) -> None:
        """Past the cap the oldest terminal cards go first; the freshly
        upserted (active) card is never a trim candidate."""
        clock = {"t": 1000.0}
        monkeypatch.setattr(digest_module.time, "time", lambda: clock["t"])
        store = DigestStore()
        for i in range(store._MAX_CARDS):
            clock["t"] += 1.0
            store.upsert(_inst(f"old{i}", status="completed"))
        assert len(store.list()) == store._MAX_CARDS
        clock["t"] += 1.0
        store.upsert(_inst("fresh", status="running"))
        cards = store.list()
        assert len(cards) == store._MAX_CARDS
        ids = {c.subagent_id for c in cards}
        assert "fresh" in ids  # the active card survived
        assert "old0" not in ids  # the oldest terminal card was evicted
        assert "old1" in ids

    def test_active_cards_are_never_evicted(self, monkeypatch) -> None:
        clock = {"t": 1000.0}
        monkeypatch.setattr(digest_module.time, "time", lambda: clock["t"])
        store = DigestStore()
        clock["t"] += 1.0
        store.upsert(_inst("ancient-but-running", status="running"))
        for i in range(store._MAX_CARDS):
            clock["t"] += 1.0
            store.upsert(_inst(f"t{i}", status="failed"))
        ids = {c.subagent_id for c in store.list()}
        assert len(ids) == store._MAX_CARDS
        assert "ancient-but-running" in ids  # non-terminal: kept despite age

    def test_cap_exceeded_with_no_evictable_card_grows(self, monkeypatch) -> None:
        """The only over-cap state the store tolerates: the new card is the
        sole terminal one (it is the active card, exempt from trimming) and
        every other card is still running — nothing evictable, so the store
        may exceed the cap rather than drop a just-updated or running card."""
        clock = {"t": 1000.0}
        monkeypatch.setattr(digest_module.time, "time", lambda: clock["t"])
        store = DigestStore()
        for i in range(store._MAX_CARDS):
            clock["t"] += 1.0
            store.upsert(_inst(f"r{i}", status="running"))
        clock["t"] += 1.0
        store.upsert(_inst("just-finished", status="completed"))
        cards = store.list()
        assert len(cards) == store._MAX_CARDS + 1
        ids = {c.subagent_id for c in cards}
        assert "just-finished" in ids
        assert "r0" in ids and f"r{store._MAX_CARDS - 1}" in ids
