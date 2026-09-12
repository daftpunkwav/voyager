"""SkillOrganizer: cadence trigger, repeated-flow detection from episodic
tool rows, confirmation-gated skill drafts, no re-proposal of saved flows."""

from __future__ import annotations

from agent.memory.episodic import EpisodicMemory
from agent.skills.loader import SkillLoader
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
    async def test_end_to_end_repeated_flow_becomes_skill(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        _seed(episodic, 3)
        asked: list[str] = []

        async def _confirm(prompt: str) -> bool:
            asked.append(prompt)
            return True

        org = SkillOrganizer(episodic, tmp_path / "skills", confirm=_confirm, settings=_Settings(1))
        hits = org.detect()
        assert hits and hits[0]["sequence"] == ["grep", "read_file"] and hits[0]["count"] == 3
        proposal = org.maybe_propose()
        assert proposal is not None
        saved = await proposal
        assert len(saved) == 1 and saved[0].name == "SKILL.md"
        assert "grep -> read_file" in asked[0]
        # The user skills directory is scanned by the loader: the draft is a real skill
        index = SkillLoader([tmp_path / "skills"]).index()
        assert any(e["name"].startswith("auto-grep-read_file") for e in index)
        # Second pass: already saved, nothing proposed again
        assert await org.propose_and_save() == []
        episodic.close()

    async def test_cadence_and_off_switch(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        _seed(episodic, 3)
        org = SkillOrganizer(episodic, tmp_path / "skills", settings=_Settings(0))
        assert org.maybe_propose() is None  # 0 = off
        org = SkillOrganizer(episodic, tmp_path / "skills", settings=_Settings(10))
        assert org.maybe_propose() is None  # 6 rows < 10
        _seed(episodic, 2)
        proposal = org.maybe_propose()
        assert proposal is not None
        await proposal
        assert org.maybe_propose() is None  # counter advanced; no new rows yet
        episodic.close()

    async def test_declined_confirmation_writes_nothing(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        _seed(episodic, 3)

        async def _no(_prompt: str) -> bool:
            return False

        org = SkillOrganizer(episodic, tmp_path / "skills", confirm=_no)
        assert await org.propose_and_save() == []
        assert not (tmp_path / "skills").exists()
        episodic.close()
