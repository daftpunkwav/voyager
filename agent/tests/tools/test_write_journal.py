"""Tests for the write journal behind the fs write tools: the backup hook is
failure-proof (a broken journal never breaks a write) and records backups.
"""

import json

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.workspace.write_journal import WriteJournal


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    (root / "repo").mkdir(exist_ok=True)
    return root


def _belt(root, journal=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root], journal=journal),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
    )


class TestJournalWiring:
    async def test_journal_failure_never_breaks_write(self, workdir) -> None:
        class _Broken:
            def capture(self, *a, **kw):
                raise RuntimeError("boom")

            def finalize(self, *a, **kw):
                raise RuntimeError("boom")

        target = workdir / "repo" / "i.txt"
        belt = _belt(workdir, journal=_Broken())  # type: ignore[arg-type]
        out = await belt.call(ToolCall("1", "write", {"path": "repo/i.txt", "content": "x"}))
        assert json.loads(out)["written"]
        assert target.read_text(encoding="utf-8") == "x"

    async def test_journal_records_backup(self, workdir, tmp_path) -> None:
        """A healthy journal snapshots the previous content of every written file."""
        journal_dir = tmp_path / "journal"
        journal = WriteJournal(journal_dir)
        target = workdir / "repo" / "b.txt"
        target.write_text("old", encoding="utf-8")
        belt = _belt(workdir, journal=journal)
        await belt.call(ToolCall("1", "write", {"path": "repo/b.txt", "content": "new"}))
        assert target.read_text(encoding="utf-8") == "new"
        # The previous content was captured somewhere under the journal dir
        backups = [p for p in journal_dir.rglob("*") if p.is_file()]
        assert backups
