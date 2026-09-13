"""Tests for the write journal and the undo_writes tool: restore semantics
per operation kind, the changed-since-write safety skip, and Toolbelt
integration (undo_writes present only when a journal is attached).
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


@pytest.fixture()
def journal(tmp_path):
    return WriteJournal(tmp_path / "journal")


async def _yes(*_args) -> bool:
    return True


def _belt(root, journal=None, confirm=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root], journal=journal),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        confirm=confirm,
    )


class TestUndoSemantics:
    async def test_undo_write_restores_previous(self, workdir, journal) -> None:
        target = workdir / "repo" / "a.txt"
        target.write_text("old", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/a.txt", "content": "new"}))
        assert target.read_text(encoding="utf-8") == "new"
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "restored" in out
        assert target.read_text(encoding="utf-8") == "old"

    async def test_undo_create_removes_file(self, workdir, journal) -> None:
        target = workdir / "repo" / "b.txt"
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/b.txt", "content": "x"}))
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "removed" in out
        assert not target.exists()

    async def test_undo_edit_restores_pre_edit(self, workdir, journal) -> None:
        target = workdir / "repo" / "c.txt"
        target.write_text("hello world\n", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(
            ToolCall(
                "1", "edit_file", {"path": "repo/c.txt", "old_text": "world", "new_text": "there"}
            )
        )
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "restored" in out
        assert target.read_text(encoding="utf-8") == "hello world\n"

    async def test_undo_delete_brings_file_back(self, workdir, journal) -> None:
        target = workdir / "repo" / "d.txt"
        target.write_text("precious", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "delete_file", {"path": "repo/d.txt"}))
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "restored" in out
        assert target.read_text(encoding="utf-8") == "precious"

    async def test_undo_counts_newest_first(self, workdir, journal) -> None:
        target = workdir / "repo" / "e.txt"
        target.write_text("v0", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/e.txt", "content": "v1"}))
        await belt.call(ToolCall("2", "write_file", {"path": "repo/e.txt", "content": "v2"}))
        await belt.call(ToolCall("3", "undo_writes", {"count": 2}))
        assert target.read_text(encoding="utf-8") == "v0"
        # a third undo has nothing left to do
        out = await belt.call(ToolCall("4", "undo_writes", {"count": 1}))
        assert "undone" in out and json.loads(out)["entries"] == []

    async def test_changed_since_write_is_skipped(self, workdir, journal) -> None:
        target = workdir / "repo" / "f.txt"
        target.write_text("old", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/f.txt", "content": "new"}))
        # mutate outside the journal: the stale restore must be refused
        target.write_text("hand-edited", encoding="utf-8")
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "skipped" in out
        assert target.read_text(encoding="utf-8") == "hand-edited"

    async def test_no_double_undo(self, workdir, journal) -> None:
        target = workdir / "repo" / "g.txt"
        target.write_text("old", encoding="utf-8")
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/g.txt", "content": "new"}))
        await belt.call(ToolCall("2", "undo_writes", {}))
        out = await belt.call(ToolCall("3", "undo_writes", {}))
        assert json.loads(out)["entries"] == []
        assert target.read_text(encoding="utf-8") == "old"

    async def test_recent_listing(self, workdir, journal) -> None:
        belt = _belt(workdir, journal, confirm=_yes)
        await belt.call(ToolCall("1", "write_file", {"path": "repo/h.txt", "content": "x"}))
        out = await belt.call(ToolCall("2", "undo_writes", {"recent": 5}))
        body = json.loads(out)
        assert body["recent"][0]["op"] == "create"
        assert (workdir / "repo" / "h.txt").exists()  # listing never undoes


class TestWiring:
    async def test_undo_tool_absent_without_journal(self, workdir) -> None:
        belt = _belt(workdir)
        assert "undo_writes" not in fs_tools([workdir])
        out = await belt.call(ToolCall("1", "undo_writes", {}))
        assert "[未知工具]" in out

    async def test_journal_failure_never_breaks_write(self, workdir, tmp_path) -> None:
        class _Broken:
            def capture(self, *a, **kw):
                raise RuntimeError("boom")

            def finalize(self, *a, **kw):
                raise RuntimeError("boom")

        target = workdir / "repo" / "i.txt"
        belt = Toolbelt(
            fs_tools([workdir], journal=_Broken()),  # type: ignore[arg-type]
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "write_file", {"path": "repo/i.txt", "content": "x"}))
        assert json.loads(out)["written"]
        assert target.read_text(encoding="utf-8") == "x"

    async def test_undo_needs_confirmation_by_default(self, workdir, journal) -> None:
        """undo_writes is a write tool: without a confirm channel it is held
        at the L2 gate rather than silently applied."""
        target = workdir / "repo" / "j.txt"
        target.write_text("old", encoding="utf-8")
        belt = Toolbelt(
            fs_tools([workdir], journal=journal),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        await belt.call(ToolCall("1", "write_file", {"path": "repo/j.txt", "content": "new"}))
        out = await belt.call(ToolCall("2", "undo_writes", {}))
        assert "[需确认]" in out
        assert target.read_text(encoding="utf-8") == "new"
