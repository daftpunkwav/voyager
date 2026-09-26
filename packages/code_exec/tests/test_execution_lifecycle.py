"""code-exec execution lifecycle: the run_snippet / run_file contract from
JobRef to store row and task.* events, plus the execution store's public
reads.

Integration tests at the capability boundary: run_in_runtime is stubbed (no
subprocess), the store, settings and event bus are real and per-test.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from code_exec import capabilities
from code_exec.capabilities import registry
from code_exec.executor import RunResult
from code_exec.store import ExecutionStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

USER_CTX = ActorContext(actor=LOCAL_USER)

_DONE = RunResult(status="completed", exit_code=0, stdout="out", stderr="", artifact_dir="a")


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Fresh service dependencies with the executor stubbed out."""
    workspace = tmp_path / "workspace"
    (workspace / "sandbox").mkdir(parents=True)
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    settings = SettingsStore(tmp_path / "settings.db", bus)
    settings.register_fresh(capabilities.DEFS)
    store = ExecutionStore(tmp_path / "code-exec.db")
    capabilities.init_deps(
        capabilities.Deps(store=store, settings=settings, bus=bus, workspace=workspace)
    )
    yield {"store": store, "bus": bus, "log": log, "workspace": workspace}
    store.close()
    settings.close()
    log.close()


async def _await_background() -> None:
    """Wait for the fire-and-forget execution tasks to settle."""
    tasks = list(capabilities._bg_tasks)
    if tasks:
        await asyncio.gather(*tasks)


def _events(log: EventLog, type_: str) -> list[dict]:
    return [e.payload for _, e in log.read_after(types=[type_])]


class TestRunLifecycle:
    async def test_completed_run_persists_and_emits(self, wired, monkeypatch) -> None:
        """A completed snippet lands as a finished store row and emits
        progress(0) -> progress(1) -> task.completed with the summary."""
        seen: dict = {}

        async def runner(runtime, code, **kwargs):
            seen.update(runtime_id=runtime["id"], code=code, timeout=kwargs["timeout"])
            return _DONE

        monkeypatch.setattr(capabilities, "run_in_runtime", runner)
        ref = await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})
        await _await_background()
        row = wired["store"].get(ref.job_id)
        assert row is not None
        assert row["status"] == "completed" and row["exit_code"] == 0 and row["stdout"] == "out"
        assert row["runtime"] == "python" and row["kind"] == "snippet"
        assert seen["runtime_id"] == "python" and seen["code"] == "x" and seen["timeout"] == 60
        assert [p["progress"] for p in _events(wired["log"], "task.progress")] == [0.0, 1.0]
        completed = _events(wired["log"], "task.completed")
        assert completed and completed[0]["result"]["exec_id"] == ref.job_id

    async def test_runner_exception_records_failed(self, wired, monkeypatch) -> None:
        """An exception inside the runner degrades to a failed row and a
        task.failed event (the background task must never die silently)."""

        async def boom(runtime, code, **kwargs):
            raise RuntimeError("runtime exploded")

        monkeypatch.setattr(capabilities, "run_in_runtime", boom)
        ref = await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})
        await _await_background()
        row = wired["store"].get(ref.job_id)
        assert row is not None
        assert row["status"] == "failed" and row["exit_code"] == -1
        assert "RuntimeError: runtime exploded" in row["stderr"]
        failed = _events(wired["log"], "task.failed")
        assert failed and "runtime exploded" in failed[0]["error"]

    async def test_non_completed_status_emits_failed_event(self, wired, monkeypatch) -> None:
        """A runner-level timeout returns a result, not an exception: the row
        keeps the runner status and task.failed carries the stderr."""
        timed_out = RunResult(
            status="timeout", exit_code=-1, stdout="", stderr="timed out", artifact_dir=""
        )

        async def runner(runtime, code, **kwargs):
            return timed_out

        monkeypatch.setattr(capabilities, "run_in_runtime", runner)
        ref = await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})
        await _await_background()
        assert wired["store"].get(ref.job_id)["status"] == "timeout"
        failed = _events(wired["log"], "task.failed")
        assert failed and failed[0]["error"] == "timed out"

    async def test_run_file_reads_sandbox_file(self, wired, monkeypatch) -> None:
        """run_file executes the file's content (read off the event loop) for
        paths under workspace/sandbox/."""
        seen: dict = {}

        async def runner(runtime, code, **kwargs):
            seen["code"] = code
            return _DONE

        monkeypatch.setattr(capabilities, "run_in_runtime", runner)
        target = Path(wired["workspace"]) / "sandbox" / "script.py"
        target.write_text("print('from file')\n", encoding="utf-8", newline="\n")
        ref = await execute(
            registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "script.py"}
        )
        await _await_background()
        assert seen["code"] == "print('from file')\n"
        assert wired["store"].get(ref.job_id)["status"] == "completed"

    async def test_run_file_rejects_absolute_escape(self, wired) -> None:
        """An absolute path outside the sandbox is an invalid input, not a
        silent read of an arbitrary file."""
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "run_file",
                USER_CTX,
                {"runtime": "python", "file_path": "/etc/passwd"},
            )
        assert exc.value.body.code == "CODE_EXEC.INVALID_INPUT"

    async def test_missing_deps_rejects_immediately(self, monkeypatch) -> None:
        """Before service wiring there is no store to record into: the call
        fails fast instead of half-starting an execution."""
        monkeypatch.setattr(capabilities, "_deps", None)
        with pytest.raises(RuntimeError, match="deps not injected"):
            await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})


class TestExecutionStore:
    def test_get_and_list_recent(self, tmp_path) -> None:
        store = ExecutionStore(tmp_path / "exec.db")
        store.create("e1", "python", kind="snippet")
        time.sleep(0.05)  # created_ts has coarse resolution on Windows
        store.create("e2", "node", kind="file")
        store.finish("e1", "completed", 0, "out", "", "art/e1")
        rows = store.list_recent()
        assert [r["id"] for r in rows] == ["e2", "e1"]  # newest first
        first = store.get("e1")
        assert first is not None
        assert first == {
            "id": "e1",
            "runtime": "python",
            "kind": "snippet",
            "status": "completed",
            "exit_code": 0,
            "stdout": "out",
            "stderr": "",
            "artifact_dir": "art/e1",
            "created_ts": first["created_ts"],
            "updated_ts": first["updated_ts"],
        }
        assert store.get("missing") is None
        store.close()
