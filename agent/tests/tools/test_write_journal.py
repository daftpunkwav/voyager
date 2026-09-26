"""Tests for the write journal behind the fs write tools: the backup hook is
failure-proof (a broken journal never breaks a write), records backups, and
the undo path restores/skips per the post-state safety rule.

Test type: unit (WriteJournal in isolation against temp dirs) plus the
tool-wiring integration covered by TestJournalWiring.
"""

import json
import threading

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.workspace.write_journal import (
    WriteJournal,
    safe_capture,
    safe_finalize,
)


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


def _journal(tmp_path) -> WriteJournal:
    return WriteJournal(tmp_path / "journal")


class TestCaptureAndFinalize:
    def test_capture_existing_file_records_write_with_blob(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "f.txt"
        target.write_text("old", encoding="utf-8")
        entry = journal.capture(target, "write")
        assert entry is not None
        rows = journal.recent()
        assert len(rows) == 1 and rows[0].op == "write"
        assert rows[0].pre_sha is not None and rows[0].post_sha is None
        assert rows[0].undone is False
        blob = tmp_path / "journal" / "blobs" / f"{rows[0].pre_sha}.bin"
        assert blob.read_text(encoding="utf-8") == "old"

    def test_capture_missing_file_journals_as_create_without_blob(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        entry = journal.capture(tmp_path / "new.txt", "write")
        assert entry is not None
        row = journal.recent()[0]
        assert row.op == "create" and row.pre_sha is None and row.blob is None

    def test_capture_delete_intent_records_delete_with_blob(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "doomed.txt"
        target.write_text("bye", encoding="utf-8")
        journal.capture(target, "delete")
        row = journal.recent()[0]
        assert row.op == "delete" and row.pre_sha is not None and row.blob is not None

    def test_finalize_records_post_state_hash(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "f.txt"
        target.write_text("before", encoding="utf-8")
        entry = journal.capture(target, "write")
        target.write_text("after", encoding="utf-8")
        journal.finalize(entry, target)
        row = journal.recent()[0]
        assert row.post_sha is not None and row.post_sha != row.pre_sha

    def test_finalize_and_capture_are_best_effort(self, tmp_path) -> None:
        """A capture on an unreadable path (a directory) returns None instead
        of raising into the write path."""
        journal = _journal(tmp_path)
        assert journal.capture(tmp_path, "write") is None
        journal.finalize(None, tmp_path / "whatever")  # no-op, never raises
        journal.finalize(999, tmp_path / "missing.txt")  # unknown entry, quiet


class TestUndo:
    def test_undo_write_restores_previous_content(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "f.txt"
        target.write_text("v1", encoding="utf-8")
        entry = journal.capture(target, "write")
        target.write_text("v2", encoding="utf-8")
        journal.finalize(entry, target)
        out = journal.undo()
        assert out["undone"] == 1
        assert out["entries"][0]["result"] == "restored previous content"
        assert target.read_text(encoding="utf-8") == "v1"
        assert journal.recent()[0].undone is True

    def test_undo_skips_file_changed_since_the_write(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "f.txt"
        entry = journal.capture(target, "write")  # create: no previous content
        target.write_text("v1", encoding="utf-8")
        journal.finalize(entry, target)
        target.write_text("v2", encoding="utf-8")  # changed after finalize
        out = journal.undo()
        assert out["entries"][0]["result"] == "skipped: file changed after this write"
        assert target.read_text(encoding="utf-8") == "v2"
        assert journal.recent()[0].undone is False  # stays eligible, never half-undone

    def test_undo_create_removes_the_created_file(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "new.txt"
        entry = journal.capture(target, "write")
        target.write_text("created", encoding="utf-8")
        journal.finalize(entry, target)
        out = journal.undo()
        assert out["entries"][0]["result"] == "removed created file"
        assert not target.exists()

    def test_undo_delete_restores_the_deleted_file(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "gone.txt"
        target.write_text("resurrect me", encoding="utf-8")
        entry = journal.capture(target, "delete")
        target.unlink()
        journal.finalize(entry, target)
        out = journal.undo()
        assert out["entries"][0]["result"] == "restored deleted file"
        assert target.read_text(encoding="utf-8") == "resurrect me"

    def test_undo_delete_refused_when_path_re_occupied(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        target = tmp_path / "gone.txt"
        target.write_text("bye", encoding="utf-8")
        journal.capture(target, "delete")
        target.unlink()
        target.write_text("someone else moved in", encoding="utf-8")
        out = journal.undo()
        assert out["entries"][0]["result"] == "skipped: path re-occupied after delete"
        assert target.read_text(encoding="utf-8") == "someone else moved in"

    def test_undo_delete_without_backup_skips(self, tmp_path) -> None:
        """A delete entry without backup content (blob lost) reports the skip
        instead of crashing; capture refuses to record a blobless delete, so
        the state is crafted directly in the index."""
        journal = _journal(tmp_path)
        target = tmp_path / "ghost.txt"
        target.write_text("data", encoding="utf-8")
        entry = journal.capture(target, "delete")
        assert entry is not None
        with journal._lock:
            journal._db.execute("UPDATE writes SET blob = NULL WHERE seq = ?", (entry,))
            journal._db.commit()
        target.unlink()
        out = journal.undo()
        assert out["entries"][0]["result"] == "skipped: no backup content"

    def test_undo_skips_when_backup_blob_was_pruned(self, tmp_path) -> None:
        import shutil

        journal = _journal(tmp_path)
        target = tmp_path / "f.txt"
        target.write_text("v1", encoding="utf-8")
        entry = journal.capture(target, "write")
        target.write_text("v2", encoding="utf-8")
        journal.finalize(entry, target)
        shutil.rmtree(tmp_path / "journal" / "blobs")
        out = journal.undo()
        assert out["entries"][0]["result"] == "skipped: backup blob missing"

    def test_undo_rolls_back_newest_first_across_entries(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        first, second = tmp_path / "a.txt", tmp_path / "b.txt"
        first.write_text("a1", encoding="utf-8")
        journal.capture(first, "write")
        second.write_text("b1", encoding="utf-8")
        journal.capture(second, "write")
        first.write_text("a2", encoding="utf-8")
        second.write_text("b2", encoding="utf-8")
        journal.finalize(1, first)
        journal.finalize(2, second)
        out = journal.undo(count=2)
        assert [e["path"] for e in out["entries"]] == [str(second), str(first)]
        assert first.read_text(encoding="utf-8") == "a1"
        assert second.read_text(encoding="utf-8") == "b1"

    def test_undo_of_inconsistent_create_entry_refuses_to_delete(self, tmp_path) -> None:
        """A create entry that somehow carries a backup blob is refused: the
        safety rule never deletes on a contradictory record."""
        journal = _journal(tmp_path)
        target = tmp_path / "odd.txt"
        entry = journal.capture(target, "write")  # create (no file yet)
        target.write_text("content", encoding="utf-8")
        journal.finalize(entry, target)
        sha = journal.recent()[0].post_sha  # read outside the lock (not reentrant)
        with journal._lock:  # same lock domain as the module's own writers
            journal._db.execute(
                "UPDATE writes SET op = 'create', blob = ? WHERE seq = ?", (f"{sha}.bin", entry)
            )
            journal._db.commit()
        out = journal.undo()
        assert out["entries"][0]["result"] == "skipped: create entry carries backup"
        assert target.exists()


class TestCrossThreadSerialization:
    def test_captures_from_many_threads_all_recorded(self, tmp_path) -> None:
        """Tool handlers run on worker threads: the lock must serialize blob +
        index writes so no capture is lost."""
        journal = _journal(tmp_path)

        def worker(n: int) -> None:
            for i in range(10):
                path = tmp_path / f"w{n}_{i}.txt"
                path.write_text(f"w{n}-{i}", encoding="utf-8")
                assert journal.capture(path, "write") is not None

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(journal.recent(limit=100)) == 40


class TestSafeGuards:
    def test_none_journal_is_a_no_op(self, tmp_path) -> None:
        path = tmp_path / "f.txt"
        assert safe_capture(None, path, "write") is None
        safe_finalize(None, 1, path)  # must not raise

    def test_foreign_journal_failures_are_swallowed(self, tmp_path) -> None:
        class _Broken:
            def capture(self, *_a, **_k):
                raise RuntimeError("boom")

            def finalize(self, *_a, **_k):
                raise RuntimeError("boom")

        path = tmp_path / "f.txt"
        assert safe_capture(_Broken(), path, "write") is None  # type: ignore[arg-type]
        safe_finalize(_Broken(), 1, path)  # type: ignore[arg-type]  # must not raise

    def test_healthy_journal_flows_through_the_guards(self, tmp_path) -> None:
        journal = _journal(tmp_path)
        path = tmp_path / "f.txt"
        path.write_text("x", encoding="utf-8")
        entry = safe_capture(journal, path, "write")
        assert entry is not None
        safe_finalize(journal, entry, path)
        assert journal.recent()[0].post_sha is not None
