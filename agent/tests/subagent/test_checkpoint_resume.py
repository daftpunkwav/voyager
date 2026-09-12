"""Tests for the checkpoint resume backend: boot to PAUSED, the resumable
list, instance rebuild, rejection paths, and mid-turn incremental saves with
continuation.

Scope: task-type + non-conversational + mode=react; conversational / snapshot-less /
other modes / terminal states return explicit errors. Every step saves incrementally, so
a crash mid-ReAct resumes from where it stopped without re-running completed tool steps.
"""

import asyncio
import json

import pytest
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.runtime.state import CheckpointStore, ResumeSnapshot, RunState, RunStatus
from agent.subagent import Mode, TaskBook
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

USER_CTX = ActorContext(actor=LOCAL_USER)


def _snapshot(**overrides) -> ResumeSnapshot:
    base: dict = {
        "instance_id": "instabcd",
        "instance_name": "scout",
        "persona": "recon",
        "goal": "index the repo",
        "constraints": "read-only",
        "done_when": "produce a list",
        "mode": "react",
        "allowed_tools": ["list_dir"],
        "max_rounds": 5,
        "max_tool_calls": None,
        "conversational": False,
        "history": [{"role": "user", "content": "start"}],
        "active_tools": [],
    }
    base.update(overrides)
    return ResumeSnapshot(**base)


def _seed_checkpoint(
    rd,
    snap: ResumeSnapshot,
    *,
    run_id="runresum001",
    status=RunStatus.RUNNING,
    with_resume=True,
) -> RunState:
    """Pre-writes a checkpoint before boot (same directory build_agent uses)."""
    store = CheckpointStore(rd / "checkpoints")
    state = RunState(task=snap.goal, run_id=run_id, status=status)
    state.add_step("llm", "round-1", "round 1")
    if with_resume:
        state.resume = snap.to_dict()
    store.save(state)
    return state


def _build(tmp_path):
    return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())


class TestSnapshotData:
    def test_snapshot_roundtrip(self) -> None:
        snap = _snapshot(max_tool_calls=9, active_tools=["notes", "web"])
        assert ResumeSnapshot.from_dict(snap.to_dict()) == snap

    def test_phase71_fields_default_and_old_json_loads(self) -> None:
        """New fields have defaults; old JSON without the new keys still loads and is equivalent to the pre-extension snapshot."""
        snap = _snapshot()
        assert snap.pending_messages is None
        assert snap.in_turn is False
        data = snap.to_dict()
        assert "pending_messages" in data and "in_turn" in data
        old = {k: v for k, v in data.items() if k not in ("pending_messages", "in_turn")}
        assert ResumeSnapshot.from_dict(old) == snap

    def test_old_checkpoint_without_resume_loads(self, tmp_path) -> None:
        """Legacy checkpoints (no resume key) load with resume=None instead of raising."""
        cp = tmp_path / "checkpoints"
        store = CheckpointStore(cp)
        (cp / "oldrun00001.json").write_text(
            json.dumps({"task": "old task", "status": "running"}), encoding="utf-8"
        )
        state = store.load("oldrun00001")
        assert state.resume is None
        assert state.status is RunStatus.RUNNING


class TestBootAndList:
    async def test_boot_paused_and_listed(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            store = CheckpointStore(rd / "checkpoints")
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.PAUSED
            assert loaded.error == "process restarted, resumable"
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert [i["run_id"] for i in out["items"]] == [state.run_id]
            item = out["items"][0]
            assert item["status"] == "paused"
            assert item["goal"] == "index the repo"
            assert item["instance_name"] == "scout"
            assert item["mode"] == "react"
            assert item["last_step"] == "round 1"
            assert item["started_ts"] == loaded.started_ts
            # Partition contract fields
            assert item["resumable"] is True
            assert item["conversational"] is False
            assert item["in_turn"] is False
        finally:
            app.memory.close()

    async def test_list_orphans_only_abandonable(self, tmp_path) -> None:
        """Orphans (conversational / non-react with a snapshot) are listed with resumable=False (abandon only);
        legacy runs without a snapshot were marked failed at boot and are not alive."""
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        _seed_checkpoint(
            rd,
            _snapshot(conversational=True, instance_id="instchat1"),
            run_id="convres001",
        )
        _seed_checkpoint(rd, _snapshot(mode="direct"), run_id="directres01")
        _seed_checkpoint(
            rd,
            _snapshot(in_turn=True),
            run_id="inturnres01",
        )
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            by_id = {i["run_id"]: i for i in out["items"]}
            store = CheckpointStore(rd / "checkpoints")
            assert store.load("legacy00001").status is RunStatus.FAILED  # legacy is not alive
            # Conversational / other modes with a snapshot: boot mechanically flips them to PAUSED alive, listed as abandon-only orphans
            assert by_id["convres001"]["resumable"] is False
            assert by_id["convres001"]["conversational"] is True
            assert by_id["directres01"]["resumable"] is False
            # Task-type react: resumable, with the in_turn flag
            assert by_id["inturnres01"]["resumable"] is True
            assert by_id["inturnres01"]["in_turn"] is True
        finally:
            app.memory.close()


class TestResumeRun:
    async def test_resume_rebuilds_instance_without_continuing(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "resume_run", USER_CTX, {"run_id": state.run_id})
            assert out["resumed"] == "instabcd"
            assert out["continuing"] is False
            inst = app.spawner.instances["instabcd"]
            assert inst.state.run_id == state.run_id
            assert inst.status is RunStatus.PAUSED  # rebuilt without rerunning
            assert inst.history == [{"role": "user", "content": "start"}]
            assert inst.task.goal == "index the repo"
            assert inst.task.constraints == "read-only"
            assert inst.task.done_when == "produce a list"
            assert inst.task.mode is Mode.REACT
            assert inst.task.allowed_tools == ("list_dir",)
            assert inst.task.limits is not None
            assert inst.task.limits.max_rounds == 5
            assert inst.persona == "recon"
            assert inst.name == "scout"
            # A live instance already exists for this run (PAUSED counts as alive): re-resuming is rejected
            with pytest.raises(ServiceError):
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": state.run_id})
        finally:
            app.memory.close()

    async def test_resume_continue_completes_task(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(
                app.registry,
                "resume_run",
                USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            assert out["continuing"] is True
            await asyncio.sleep(0.1)
            inst = app.spawner.instances["instabcd"]
            assert inst.status is RunStatus.COMPLETED
            assert inst.state.result
            # After the continued run the checkpoint is rewritten: terminal state, gone from the resume list
            listed = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert listed["items"] == []
        finally:
            app.memory.close()


class TestMidTurnCheckpoint:
    """Mid-ReAct incremental saves -> boot to PAUSED -> resume continues from mid-turn."""

    async def test_mid_turn_save_and_resume_continues_without_redo(self, tmp_path) -> None:
        """round-1 calls a tool, crash before round-2 -> resume finishes the run with the tool called only once."""
        rd = tmp_path / "rd"
        hang = asyncio.Event()
        n_calls = {"n": 0}

        async def _script(messages, tools):
            n_calls["n"] += 1
            if n_calls["n"] == 1:  # round-1: request list_dir
                return LLMReply(
                    tool_calls=(ToolCall(id="c1", name="list_dir", arguments={"path": "."}),)
                )
            await hang.wait()  # round-2 complete hangs = the crash point
            return LLMReply(text="must not be reached")

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_script))
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="mid-turn save", mode=Mode.REACT, allowed_tools=("list_dir",)),
                persona="recon",
                name="scout",
            )
            # Drive run_turn directly, bypassing spawner.start: a dying process never runs start's
            # finally save, so the on-disk mid-turn snapshot of the last step must survive
            turn = asyncio.create_task(inst.run_turn())
            store = CheckpointStore(rd / "checkpoints")
            # Poll until the tool step's incremental save lands on disk (including the fresh tool row)
            for _ in range(500):
                await asyncio.sleep(0.01)
                if not (rd / "checkpoints" / f"{inst.state.run_id}.json").exists():
                    continue  # the first save point (step 1 on_step) has not happened yet
                saved = store.load(inst.state.run_id).resume
                if (
                    isinstance(saved, dict)
                    and saved.get("in_turn")
                    and any(m.get("role") == "tool" for m in saved.get("pending_messages") or [])
                ):
                    break
            else:
                pytest.fail("no mid-turn snapshot landed on disk after the tool step")
            pending = saved["pending_messages"]
            # Snapshot shape: pair-wise backfill (system first, assistant(tool_calls) grouped with its tool rows)
            assert [m["role"] for m in pending] == ["system", "assistant", "tool"]
            assert pending[1]["tool_calls"][0]["id"] == "c1"
            assert pending[2]["tool_call_id"] == "c1"
            assert inst.state.tool_calls == 1
            assert inst.state.rounds == 1

            # Simulate a killed process: hard cancel; the on-disk mid-turn snapshot must not be overwritten by a turn boundary
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
            snap = store.load(inst.state.run_id)
            assert snap is not None and snap.resume is not None
            assert snap.resume["in_turn"] is True
            assert snap.status is RunStatus.RUNNING
        finally:
            app.close()

        # "Restart": rebuild the app on the same data dir -> boot flips to PAUSED -> resume continues
        llm2 = FakeLLM(script=[LLMReply(text="directory listing done.")])
        app2 = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=llm2)
        try:
            out = await execute(
                app2.registry,
                "resume_run",
                USER_CTX,
                {"run_id": inst.state.run_id, "continue_run": True},
            )
            assert out["continuing"] is True
            await asyncio.sleep(0.1)
            inst2 = app2.spawner.instances[inst.id]
            assert inst2.status is RunStatus.COMPLETED
            assert inst2.state.result == "directory listing done."
            # The continued run performs exactly one complete (the round after the crash point);
            # list_dir is not re-executed (its result is already in the transcript)
            assert len(llm2.calls) == 1
            assert inst2.state.tool_calls == 1
            assert inst2.state.rounds == 2
            msgs = llm2.calls[0]["messages"]
            assert [m["role"] for m in msgs] == ["system", "assistant", "tool"]
            assert msgs[2]["content"] == pending[2]["content"]
            # After the run, the turn-boundary snapshot replaces the mid-turn one: in_turn reset, terminal status
            final = CheckpointStore(rd / "checkpoints").load(inst.state.run_id)
            assert final is not None and final.resume is not None
            assert final.status is RunStatus.COMPLETED
            assert final.resume["in_turn"] is False
        finally:
            app2.close()

    def test_snapshot_repairs_unpaired_tail(self, tmp_path) -> None:
        """Crash mid multi-tool round: the incomplete tail group (assistant with tool_calls but missing tool rows) rolls back as a whole."""
        app = _build(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(
                    goal="partial group rollback", mode=Mode.REACT, allowed_tools=("list_dir",)
                ),
                persona="recon",
            )
            inst._turn_messages = [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
                {"role": "tool", "tool_call_id": "a", "name": "list_dir", "content": "r1"},
            ]
            snap = inst.build_resume_snapshot(in_turn=True, pending_messages=inst._turn_messages)
            assert snap.in_turn is True
            assert [m["role"] for m in snap.pending_messages] == ["system", "user"]
            # The default call means a turn-boundary snapshot
            plain = inst.build_resume_snapshot()
            assert plain.pending_messages is None
            assert plain.in_turn is False
        finally:
            app.memory.close()

    async def test_in_turn_without_pending_falls_back_to_turn_boundary(self, tmp_path) -> None:
        """in_turn=True with missing pending_messages: falls back to plain history rebuild plus a fresh turn."""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(in_turn=True))
        app = _build(tmp_path)
        try:
            await execute(
                app.registry,
                "resume_run",
                USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            await asyncio.sleep(0.1)
            inst = app.spawner.instances["instabcd"]
            assert inst.status is RunStatus.COMPLETED
            assert inst.history[-1] == {"role": "assistant", "content": "Got it."}
        finally:
            app.memory.close()

    async def test_in_turn_corrupt_pending_rejected(self, tmp_path) -> None:
        """Structurally broken pending_messages (non-list / non-dict entries): rejected as NOT_FOUND without leaving a half-built instance."""
        rd = tmp_path / "rd"
        _seed_checkpoint(
            rd,
            _snapshot(in_turn=True, pending_messages="garbage"),
            run_id="badpend01",
        )
        _seed_checkpoint(
            rd,
            _snapshot(in_turn=True, pending_messages=[1, 2]),
            run_id="badpend02",
        )
        app = _build(tmp_path)
        try:
            for rid in ("badpend01", "badpend02"):
                with pytest.raises(ServiceError) as exc:
                    await execute(app.registry, "resume_run", USER_CTX, {"run_id": rid})
                assert exc.value.body.code == "AGENT.NOT_FOUND", rid
            assert app.spawner.instances == {}  # no half-built instance left behind on rejection
        finally:
            app.memory.close()


class TestResumeRejections:
    async def test_legacy_without_snapshot_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert out["items"] == []  # legacy was marked failed at boot, not alive
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": state.run_id})
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_conversational_snapshot_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(conversational=True), run_id="convres001")
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": "convres001"})
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_non_react_mode_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(mode="direct"), run_id="directres01")
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": "directres01"})
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_terminal_status_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(), run_id="doneresum01", status=RunStatus.COMPLETED)
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": "doneresum01"})
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_missing_checkpoint_rejected(self, tmp_path) -> None:
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "resume_run", USER_CTX, {"run_id": "nosuchrun1"})
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_corrupt_snapshot_rejected_and_not_listed(self, tmp_path) -> None:
        """Corrupt snapshots (missing required keys) / non-dict: skipped by the list, rejected as NOT_FOUND by resume, never a raw TypeError."""
        rd = tmp_path / "rd"
        store = CheckpointStore(rd / "checkpoints")
        for rid, bad_resume in (
            (
                "corruptres1",
                {"mode": "react", "goal": "missing id"},
            ),  # missing instance_id and other required keys
            ("corruptres2", "garbage"),  # not a dict
        ):
            st = RunState(task="bad snapshot", run_id=rid, status=RunStatus.RUNNING)
            st.resume = bad_resume  # type: ignore[assignment]  # intentionally corrupt
            store.save(st)
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert out["items"] == []
            for rid in ("corruptres1", "corruptres2"):
                with pytest.raises(ServiceError) as exc:
                    await execute(app.registry, "resume_run", USER_CTX, {"run_id": rid})
                assert exc.value.body.code == "AGENT.NOT_FOUND", rid
        finally:
            app.memory.close()


class TestAbandonCheckpoint:
    """Abandoning a resumable checkpoint: deletes the file and clears the in-memory instance, same rules as resume_run."""

    async def test_abandon_deletes_file_and_empties_list(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(
                app.registry,
                "abandon_resumable_checkpoint",
                USER_CTX,
                {"run_id": state.run_id},
            )
            assert out == {"abandoned": state.run_id}
            # The on-disk file is gone and the run no longer appears in the list
            assert not (rd / "checkpoints" / f"{state.run_id}.json").exists()
            listed = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert listed["items"] == []
        finally:
            app.memory.close()

    async def test_abandon_missing_run_not_found(self, tmp_path) -> None:
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "abandon_resumable_checkpoint",
                    USER_CTX,
                    {"run_id": "nosuchrun1"},
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_abandon_legacy_without_snapshot_not_found(self, tmp_path) -> None:
        """Legacy runs without a snapshot cannot be abandoned, consistent with resume_run (NOT_FOUND)."""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "abandon_resumable_checkpoint",
                    USER_CTX,
                    {"run_id": state.run_id},
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
            # Rejection must not delete the file
            assert (rd / "checkpoints" / "legacy00001.json").exists()
        finally:
            app.memory.close()

    async def test_abandon_allows_conversational_snapshot(self, tmp_path) -> None:
        """Orphans (conversational with a valid snapshot) are listed with resumable=False and can be
        abandoned: the only cleanup channel, while resume still rejects them."""
        rd = tmp_path / "rd"
        _seed_checkpoint(
            rd,
            _snapshot(conversational=True, instance_id="instchat1"),
            run_id="convres001",
        )
        app = _build(tmp_path)
        try:
            listed = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            item = next(i for i in listed["items"] if i["run_id"] == "convres001")
            assert item["resumable"] is False  # listed for visibility, abandon only
            out = await execute(
                app.registry,
                "abandon_resumable_checkpoint",
                USER_CTX,
                {"run_id": "convres001"},
            )
            assert out == {"abandoned": "convres001"}
            assert not (rd / "checkpoints" / "convres001.json").exists()
        finally:
            app.memory.close()

    async def test_abandon_after_resume_removes_instance(self, tmp_path) -> None:
        """Abandoning after a resume rebuild (PAUSED counts as alive): the instance disappears from list_subagents and the file is deleted."""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            await execute(app.registry, "resume_run", USER_CTX, {"run_id": state.run_id})
            running = (await execute(app.registry, "list_subagents", USER_CTX, {}))["running"]
            assert any(r["id"] == "instabcd" for r in running)

            await execute(
                app.registry,
                "abandon_resumable_checkpoint",
                USER_CTX,
                {"run_id": state.run_id},
            )
            running = (await execute(app.registry, "list_subagents", USER_CTX, {}))["running"]
            assert all(r["id"] != "instabcd" for r in running)
            assert state.run_id not in app.spawner.instances
        finally:
            app.memory.close()


class TestSnapshotOnSave:
    async def test_task_turn_end_checkpoint_has_snapshot(self, tmp_path) -> None:
        """New saves carry a resume snapshot; completed runs are not alive."""
        app = _build(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="small task", mode=Mode.REACT, allowed_tools=("list_dir",)),
                persona="recon",
                name="small task",
            )
            await app.spawner.start(inst)
            loaded = CheckpointStore(tmp_path / "rd" / "checkpoints").load(inst.state.run_id)
            assert loaded.status is RunStatus.COMPLETED
            assert loaded.resume is not None
            assert loaded.resume["goal"] == "small task"
            assert loaded.resume["instance_id"] == inst.id
            assert loaded.resume["mode"] == "react"
            assert loaded.resume["conversational"] is False
        finally:
            app.memory.close()


class TestResumeContinueFailureVisible:
    """Background continuation failures stay visible: a task.failed event is emitted and the disk state lands on FAILED, never swallowed."""

    async def test_continue_failure_emits_task_failed_and_persists_failed(
        self,
        tmp_path,
    ) -> None:
        rd = tmp_path / "rd"

        async def _boom(messages, tools):
            raise RuntimeError("LLM blew up during resume")

        state = _seed_checkpoint(rd, _snapshot())
        app = build_agent(
            data_dir=rd,
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(dynamic=_boom),
        )
        try:
            out = await execute(
                app.registry,
                "resume_run",
                USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            assert out["continuing"] is True
            await asyncio.sleep(0.2)

            store = CheckpointStore(rd / "checkpoints")
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.FAILED
            assert "RuntimeError" in loaded.error
            assert loaded not in store.list_alive()

            evs = app.log.read_after(after_seq=0)
            failed = [e for _, e in evs if e.type == "task.failed"]
            assert any(
                e.payload.get("run_id") == state.run_id
                and e.payload.get("kind") == "resume"
                and "RuntimeError" in e.payload.get("error", "")
                for e in failed
            )
            assert any(
                e.payload.get("kind") == "resume" and e.payload.get("title") == "scout"
                for e in failed
            )
            # job_id=run_id: the UI's taskKey needs source_id/job_id to build its card; without it the card is dropped
            assert any(e.payload.get("job_id") == state.run_id for e in failed)
        finally:
            app.memory.close()

    async def test_success_path_still_completes_and_clears(self, tmp_path) -> None:
        """Success-path regression: a finished continuation -> checkpoint COMPLETED and gone from the resume list."""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = build_agent(
            data_dir=rd,
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(script=[LLMReply(text="resumed successfully.")]),
        )
        try:
            await execute(
                app.registry,
                "resume_run",
                USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            await asyncio.sleep(0.2)
            store = CheckpointStore(rd / "checkpoints")
            assert store.load(state.run_id).status is RunStatus.COMPLETED
            listed = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert listed["items"] == []
            failed_evs = [
                e
                for _, e in app.log.read_after(after_seq=0)
                if e.type == "task.failed" and e.payload.get("kind") == "resume"
            ]
            assert failed_evs == []
        finally:
            app.memory.close()
