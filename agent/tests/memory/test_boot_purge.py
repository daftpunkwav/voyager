"""Boot-time retention purge: expired episodic rows are removed at startup
without requiring the settings page to be opened first."""

import sqlite3
import time
from pathlib import Path

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.memory import EpisodicMemory
from agent.settings import DEFS as AGENT_SETTING_DEFS
from platform_contracts import LOCAL_USER
from platform_settings import SettingsStore


class TestBootEpisodicPurge:
    """Boot purges expired episodes per retention, without requiring the user to open settings first."""

    @staticmethod
    def _seed(rd: Path, *, expired: bool) -> None:
        """Seeds two episodes; with expired=True the first one's ts is backdated 365 days."""
        db = rd / "memory" / "episodic.db"
        epi = EpisodicMemory(db)
        epi.log("consider", "long-ago event")
        epi.log("consider", "recent event")
        if expired:
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "UPDATE episodes SET ts = ? WHERE summary = ?",
                    (time.time() - 365 * 86400, "long-ago event"),
                )
                conn.commit()
            finally:
                conn.close()
        epi.close()

    async def _preset_retention(self, rd: Path, days: int) -> None:
        """Pre-writes retention before build (same database and registration path as build_agent)."""
        store = SettingsStore(rd / "settings.db")
        store.register_fresh(AGENT_SETTING_DEFS)
        await store.set("agent.memory.retention_days", days, LOCAL_USER)
        store.close()

    async def test_boot_purges_expired_episodes(self, tmp_path) -> None:
        """With retention>0, build_agent purges expired episodes during assembly and keeps fresh ones."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 30)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" not in summaries
            assert "recent event" in summaries
        finally:
            app.memory.close()

    async def test_boot_purge_zero_retention_is_noop(self, tmp_path) -> None:
        """retention=0 means agent-managed: boot does not purge, expired entries are kept."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 0)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" in summaries
            assert "recent event" in summaries
        finally:
            app.memory.close()
