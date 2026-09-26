"""Checkpoint store lifecycle: crash-status reclaim, atomic tmp+replace
writes, and the startup sweep of orphan .tmp files."""

import os

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime.state import (
    CheckpointStore,
    ResumeSnapshot,
    RunState,
    RunStatus,
    reclaim_alive,
)


class TestReclaim:
    def test_reclaim_marks_running_failed(self, tmp_path) -> None:
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        out = reclaim_alive(store)

        assert len(out) == 1
        assert store.list_alive() == []
        loaded = store.load(state.run_id)
        assert loaded.status is RunStatus.FAILED
        assert loaded.error == "process restarted, task not recovered"

    def test_reclaim_noop_on_empty_store(self, tmp_path) -> None:
        assert reclaim_alive(CheckpointStore(tmp_path / "cp")) == []

    async def test_build_agent_reclaims_on_boot(self, tmp_path) -> None:
        """build_agent boot semantics: a legacy alive run without a resume snapshot -> FAILED;
        an alive run with a resume snapshot -> PAUSED awaiting recovery, still in list_alive."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        store = CheckpointStore(cp_dir)
        legacy = RunState(task="t")
        legacy.status = RunStatus.RUNNING
        legacy.run_id = "legacy000001"
        store.save(legacy)
        snap = ResumeSnapshot(
            instance_id="inst0001",
            instance_name="scout",
            persona="recon",
            goal="index the repo",
            history=[{"role": "user", "content": "start"}],
        )
        resumable = RunState(
            task=snap.goal,
            run_id="resume00001",
            status=RunStatus.RUNNING,
            resume=snap.to_dict(),
        )
        store.save(resumable)

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            loaded = store.load(legacy.run_id)
            assert loaded.status is RunStatus.FAILED
            assert loaded.error == "process restarted, task not recovered"
            kept = store.load(resumable.run_id)
            assert kept.status is RunStatus.PAUSED
            assert kept.error == "process restarted, resumable"
            assert {s.run_id for s in store.list_alive()} == {resumable.run_id}
        finally:
            app.memory.close()

    def test_build_agent_skips_broken_checkpoint(self, tmp_path) -> None:
        """Boot assembly survives broken JSON mixed into the checkpoint directory; valid alive runs still get marked failed and the bad file is preserved."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / "broken.json").write_text("{not json", encoding="utf-8")
        store = CheckpointStore(cp_dir)
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert store.list_alive() == []
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.FAILED
            # The broken file is kept as-is: no unlink, no rewrite
            assert (cp_dir / "broken.json").read_text(encoding="utf-8") == "{not json"
        finally:
            app.memory.close()


class TestCheckpointAtomicWrites:
    """Atomic writes: save goes through tmp + os.replace, so readers always see a whole file."""

    def test_save_is_atomic_and_no_tmp_left(self, tmp_path) -> None:
        """After save the target is valid JSON and no orphan .tmp files remain in the directory."""
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="atomic write", status=RunStatus.RUNNING)
        state.add_step("llm", "round-1", "round 1")

        store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "atomic write"
        assert loaded.status is RunStatus.RUNNING
        assert len(loaded.steps) == 1
        leftovers = [p.name for p in (tmp_path / "cp").glob("*.tmp")]
        assert leftovers == []

    def test_save_does_not_truncate_existing_target(self, tmp_path, monkeypatch) -> None:
        """When the target exists, the old file stays intact until replace succeeds: the half-written
        window is confined to the tmp file (monkeypatch fails the first replace; save raises, the
        old JSON stays readable, and a subsequent save overwrites successfully)."""
        import agent.runtime.state as state_mod

        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="v1", status=RunStatus.RUNNING)
        state.run_id = "atomicsave01"
        store.save(state)

        real_replace = os.replace
        failed = {"n": 0}

        def _flaky_replace(src, dst):
            if failed["n"] == 0 and str(dst).endswith("atomicsave01.json"):
                failed["n"] += 1
                raise OSError("simulated replace failure")
            return real_replace(src, dst)

        monkeypatch.setattr(state_mod.os, "replace", _flaky_replace)
        state.task = "v2"
        with pytest.raises(OSError):  # a replace failure propagates out of save to the caller
            store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "v1"  # the old whole file was not truncated

        monkeypatch.setattr(state_mod.os, "replace", real_replace)
        store.save(state)  # retry succeeds
        assert store.load(state.run_id).task == "v2"

    def test_concurrent_saves_then_load_valid(self, tmp_path) -> None:
        """Concurrent saves for the same run: the target file is always some complete write (load never
        crashes); even when concurrent os.replace occasionally races on Windows, the target is never half-written."""
        from concurrent.futures import ThreadPoolExecutor

        store = CheckpointStore(tmp_path / "cp")
        store.save(RunState(task="v0", status=RunStatus.RUNNING, run_id="concurrent1"))

        def _save(i: int) -> None:
            for _ in range(5):
                st = RunState(task=f"v{i}", status=RunStatus.RUNNING)
                st.run_id = "concurrent1"
                try:
                    store.save(st)
                except OSError:
                    # Concurrent replace on Windows can raise PermissionError:
                    # single-threaded production never hits it; an individual failed save is not a half-written file
                    pass

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_save, range(50)))

        loaded = store.load("concurrent1")  # must not raise JSONDecodeError
        assert loaded.status is RunStatus.RUNNING
        assert loaded.task.startswith("v")
        # Exactly one target file remains; leftover .tmp files do not affect list_alive (it globs *.json only)
        assert [p.name for p in (tmp_path / "cp").glob("*.json")] == ["concurrent1.json"]
        assert {s.run_id for s in store.list_alive()} == {"concurrent1"}


class TestCheckpointTmpPurge:
    """Startup purge of orphan .tmp files: only save-shaped names, single directory level."""

    def test_purge_tmp_removes_only_orphan_tmp(self, tmp_path) -> None:
        """Deletes `.{run_id}.json.{hex}.tmp` shapes; valid json, unrelated .tmp, and subdirectories are untouched."""
        cp = tmp_path / "cp"
        store = CheckpointStore(cp)
        state = RunState(task="t", status=RunStatus.PAUSED)
        store.save(state)  # atomic write lands cleanly, no residue
        (cp / f".{state.run_id}.json.deadbeef.tmp").write_text("residue1", encoding="utf-8")
        (cp / ".abc123.json.cafe1234.tmp").write_text("residue2", encoding="utf-8")
        (cp / "foo.tmp").write_text("not save-shaped", encoding="utf-8")
        (cp / "broken.json").write_text("{bad", encoding="utf-8")
        sub = cp / "sub"
        sub.mkdir()
        (sub / ".x.json.aaaabbbb.tmp").write_text("subdir not purged", encoding="utf-8")

        removed = store.purge_tmp()

        assert removed == 2
        assert (cp / f"{state.run_id}.json").is_file()  # valid checkpoint untouched
        assert (cp / "broken.json").is_file()  # broken json untouched as well
        assert (cp / "foo.tmp").is_file()  # non-save shapes are not deleted
        assert (sub / ".x.json.aaaabbbb.tmp").is_file()  # no recursion
        assert list(cp.glob(".*.json.*.tmp")) == []

    def test_purge_tmp_noop_on_empty_store(self, tmp_path) -> None:
        assert CheckpointStore(tmp_path / "cp").purge_tmp() == 0

    async def test_build_agent_purges_tmp_on_boot(self, tmp_path) -> None:
        """build_agent purges orphan .tmp files once during assembly without blocking startup."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / ".orphan000001.json.deadbeef.tmp").write_text("{}", encoding="utf-8")

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert list(cp_dir.glob(".*.json.*.tmp")) == []
        finally:
            app.memory.close()
