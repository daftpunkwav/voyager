"""SkillOrganizer: cadence trigger, repeated-flow detection from episodic
tool rows, non-blocking skill.proposed notifications, no re-proposal of an
already-surfaced flow, and exclusion of single-tool loops."""

from __future__ import annotations

from agent.memory.episodic import EpisodicMemory
from agent.skills.organizer import SkillOrganizer


class _Settings:
    def __init__(self, every: int) -> None:
        self.every = every

    def get(self, key: str):
        return self.every if key == "agent.skills.organize_every" else None


def _seed(episodic: EpisodicMemory, runs: int) -> None:
    for i in range(runs):
        for tool in ("grep", "read_file"):
            episodic.log("tool", tool, {"ok": True}, run_id=f"r{i}")


class TestOrganizer:
    async def test_repeated_flow_is_proposed_once_via_event(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        _seed(episodic, 3)
        published: list[dict] = []

        async def _emit(type_: str, **payload) -> None:
            published.append({"type": type_, **payload})

        org = SkillOrganizer(episodic, emit=_emit, settings=_Settings(1))
        hits = org.detect()
        assert hits and hits[0]["sequence"] == ["grep", "read_file"] and hits[0]["count"] == 3
        proposal = org.maybe_propose()
        assert proposal is not None
        out = await proposal
        assert len(published) == 1
        assert published[0]["type"] == "skill.proposed"
        assert published[0]["sequence"] == ["grep", "read_file"]
        assert published[0]["count"] == 3
        assert out == [
            {"name": "auto-grep-read_file", "sequence": ["grep", "read_file"], "count": 3}
        ]
        # No file is written at proposal time: saving is propose_skill's job
        assert not (tmp_path / "skills").exists()
        # Second pass: the same flow is not re-surfaced
        assert await org.propose() == []
        episodic.close()

    async def test_single_tool_loop_is_not_a_flow(self, tmp_path) -> None:
        """A repeated identical call is a loop, not a skill candidate."""
        episodic = EpisodicMemory(tmp_path / "e.db")
        for i in range(6):
            episodic.log("tool", "settings__set_theme", {"ok": True}, run_id=f"r{i % 2}")
        org = SkillOrganizer(episodic, settings=None)
        assert org.detect() == []
        episodic.close()

    async def test_cadence_and_off_switch(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        _seed(episodic, 3)
        org = SkillOrganizer(episodic, emit=None, settings=_Settings(0))
        assert org.maybe_propose() is None  # 0 = off
        org = SkillOrganizer(episodic, emit=_sink, settings=_Settings(10))
        assert org.maybe_propose() is None  # 6 rows < 10
        _seed(episodic, 2)
        proposal = org.maybe_propose()
        assert proposal is not None
        await proposal
        assert org.maybe_propose() is None  # counter advanced; no new rows yet
        episodic.close()


async def _sink(*_a, **_k) -> None:
    return None
