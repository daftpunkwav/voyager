"""Boot-time retention purge: expired episodic rows AND expired semantic
facts are removed at startup without requiring the settings page to be
opened first."""

import sqlite3
import time
from pathlib import Path

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.memory import EpisodicMemory, SemanticMemory
from agent.settings import DEFS as AGENT_SETTING_DEFS
from platform_contracts import LOCAL_USER
from platform_settings import SettingsStore


class TestBootEpisodicPurge:
    """Boot purges expired episodes and semantic facts per retention, without
    requiring the user to open settings first."""

    @staticmethod
    def _seed(rd: Path, *, expired: bool) -> None:
        """Seeds two episodes and two semantic facts; with expired=True the
        first of each is backdated 365 days."""
        db = rd / "memory" / "episodic.db"
        epi = EpisodicMemory(db)
        epi.log("consider", "long-ago event")
        epi.log("consider", "recent event")
        facts = rd / "memory" / "semantic.db"
        sem = SemanticMemory(facts)
        sem.add("old-topic", "uses", "v1")
        sem.add("fresh-topic", "uses", "v2")
        if expired:
            cutoff = time.time() - 365 * 86400
            backdated = (
                (db, "UPDATE episodes SET ts = ? WHERE summary = ?", "long-ago event"),
                (facts, "UPDATE facts SET ts = ? WHERE subject = ?", "old-topic"),
            )
            for path, statement, key in backdated:
                conn = sqlite3.connect(str(path))
                try:
                    conn.execute(statement, (cutoff, key))
                    conn.commit()
                finally:
                    conn.close()
        epi.close()
        sem.close()

    async def _preset_retention(self, rd: Path, days: int) -> None:
        """Pre-writes retention before build (same database and registration path as build_agent)."""
        store = SettingsStore(rd / "settings.db")
        store.register_fresh(AGENT_SETTING_DEFS)
        await store.set("agent.memory.retention_days", days, LOCAL_USER)
        store.close()

    async def test_boot_purges_expired_episodes_and_facts(self, tmp_path) -> None:
        """With retention>0, build_agent purges expired episodes and semantic
        facts during assembly and keeps the fresh ones."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 30)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" not in summaries
            assert "recent event" in summaries
            subjects = {f["subject"] for f in app.memory.semantic.query()}
            assert "old-topic" not in subjects
            assert "fresh-topic" in subjects
        finally:
            app.memory.close()

    async def test_boot_purge_zero_retention_is_noop(self, tmp_path) -> None:
        """retention=0 means agent-managed: boot does not purge, expired
        episodes and facts are kept."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 0)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" in summaries
            assert "recent event" in summaries
            subjects = {f["subject"] for f in app.memory.semantic.query()}
            assert {"old-topic", "fresh-topic"} <= subjects
        finally:
            app.memory.close()
