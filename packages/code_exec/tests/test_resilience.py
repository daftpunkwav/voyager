"""code-exec resilience tests: failure paths of the execution envelope.

Covers the bounded-resource discipline: concurrent-execution cap (rejection,
release on every exit path), source size caps, timeout-side container kill
(docker CLI death does not stop the container), and execution-history /
artifact retention.
"""

import asyncio
import os
import sys
import time

import pytest
from code_exec import capabilities
from code_exec.capabilities import registry
from code_exec.executor import RunResult, _execute, run_in_runtime
from code_exec.store import ExecutionStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError
from platform_settings import SettingsStore

USER_CTX = ActorContext(actor=LOCAL_USER)


@pytest.fixture()
def svc(tmp_path):
    """Wired service with a 2-slot execution cap and no bus."""
    workspace = tmp_path / "workspace"
    (workspace / "sandbox").mkdir(parents=True)
    settings = SettingsStore(tmp_path / "settings.db")
    settings.register_fresh(capabilities.DEFS)
    store = ExecutionStore(tmp_path / "exec.db")
    capabilities.init_deps(
        capabilities.Deps(
            store=store,
            settings=settings,
            bus=None,
            workspace=workspace,
            max_concurrent_executions=2,
        )
    )
    yield workspace
    store.close()
    settings.close()


async def _drain() -> None:
    """Await every outstanding fire-and-forget execution task."""
    while capabilities._bg_tasks:
        await asyncio.gather(*list(capabilities._bg_tasks))


class TestConcurrencyCap:
    async def test_over_limit_rejected_with_queue_full(self, svc, monkeypatch) -> None:
        """The third concurrent call is rejected instead of queueing without
        bound: each accepted call holds a container/host process. Completion
        frees the slots — the freed capacity is observable at the entry point
        again (two more accepted, a third rejected)."""
        release = asyncio.Event()

        async def slow_runtime(*_args, **_kwargs) -> RunResult:
            await release.wait()
            return RunResult(status="completed", exit_code=0, stdout="", stderr="", artifact_dir="")

        monkeypatch.setattr(capabilities, "run_in_runtime", slow_runtime)
        await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x1"})
        await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x2"})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x3"})
        assert exc.value.body.code == "CODE_EXEC.QUEUE_FULL"
        release.set()
        await _drain()
        release = asyncio.Event()
        await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x4"})
        await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x5"})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x6"})
        assert exc.value.body.code == "CODE_EXEC.QUEUE_FULL"
        release.set()
        await _drain()

    async def test_run_file_reserves_from_the_same_cap(self, svc, monkeypatch) -> None:
        """run_file holds its own reserve point (after reading the file):
        the concurrent cap applies to file runs too, not just snippets."""
        sandbox = svc / "sandbox"
        (sandbox / "job.py").write_text("print('x')\n", encoding="utf-8")
        release = asyncio.Event()

        async def slow_runtime(*_args, **_kwargs) -> RunResult:
            await release.wait()
            return RunResult(status="completed", exit_code=0, stdout="", stderr="", artifact_dir="")

        monkeypatch.setattr(capabilities, "run_in_runtime", slow_runtime)
        await execute(registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "job.py"})
        await execute(registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "job.py"})
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "job.py"}
            )
        assert exc.value.body.code == "CODE_EXEC.QUEUE_FULL"
        release.set()
        await _drain()

    async def test_slot_released_after_failure(self, svc, monkeypatch) -> None:
        """A failed execution releases its slot: capacity is never leaked by
        the error path (the rejection above must be recoverable)."""

        async def refusing_runtime(*_args, **_kwargs) -> RunResult:
            raise ServiceError("code-exec", ErrorSuffix.UNAVAILABLE, "host mode refuses")

        monkeypatch.setattr(capabilities, "run_in_runtime", refusing_runtime)
        await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})
        await _drain()
        # The freed slot accepts a new execution immediately
        ref = await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": "x"})
        assert ref.job_id
        await _drain()


class TestCodeSizeCap:
    async def test_oversize_snippet_rejected_before_spawn(self, svc) -> None:
        big = "x" * (capabilities._MAX_CODE_CHARS + 1)
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "run_snippet", USER_CTX, {"runtime": "python", "code": big})
        assert exc.value.body.code == "CODE_EXEC.INVALID_INPUT"
        assert capabilities._bg_tasks == set()  # nothing spawned

    async def test_oversize_file_rejected(self, svc) -> None:
        sandbox = svc / "sandbox"
        (sandbox / "big.py").write_text("x" * (capabilities._MAX_CODE_CHARS + 1))
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "big.py"}
            )
        assert exc.value.body.code == "CODE_EXEC.INVALID_INPUT"
        assert capabilities._bg_tasks == set()


class TestTimeoutContainerKill:
    async def test_timeout_runs_kill_command(self, tmp_path) -> None:
        """The timeout path runs the side cleanup command after killing the
        child: killing the docker CLI alone would leave the named container
        running on the daemon. A marker file stands in for `docker kill`."""
        marker = tmp_path / "killed.marker"
        result = await _execute(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            artifact_dir=tmp_path,
            cwd=None,
            timeout=1,
            timeout_kill=[
                sys.executable,
                "-c",
                "import sys; open(sys.argv[1], 'w').close()",
                str(marker),
            ],
        )
        assert result.status == "timeout"
        assert marker.exists()  # the cleanup really ran and was reaped

    async def test_timeout_tolerates_failing_kill(self, tmp_path) -> None:
        """A cleanup command that fails (container already gone -> nonzero
        exit) never escapes the timeout path: the result is still a normal
        timeout answer."""
        result = await _execute(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            artifact_dir=tmp_path,
            cwd=None,
            timeout=1,
            timeout_kill=[sys.executable, "-c", "import sys; sys.exit(3)"],
        )
        assert result.status == "timeout"

    async def test_kill_skipped_on_success(self, tmp_path) -> None:
        """The cleanup command belongs to the timeout path only: a run that
        finishes in time must not fire it."""
        marker = tmp_path / "killed.marker"
        result = await _execute(
            [sys.executable, "-c", "print('ok')"],
            artifact_dir=tmp_path,
            cwd=None,
            timeout=30,
            timeout_kill=[
                sys.executable,
                "-c",
                "import sys; open(sys.argv[1], 'w').close()",
                str(marker),
            ],
        )
        assert result.status == "completed"
        assert not marker.exists()

    async def test_docker_run_names_container_and_kill_target(self, tmp_path, monkeypatch) -> None:
        """The docker path runs a named container and aims the timeout kill
        at that exact name: this pairing is what makes the timeout path able
        to stop an orphan container."""
        from code_exec import executor

        captured: dict = {}

        async def fake_execute(args, **kw):
            captured["args"] = list(args)
            captured["kw"] = kw
            return RunResult(status="completed", exit_code=0, stdout="", stderr="", artifact_dir="")

        monkeypatch.setattr(executor.shutil, "which", lambda name: "/usr/bin/docker")
        monkeypatch.setattr(executor, "_execute", fake_execute)
        await run_in_runtime(
            {"id": "python", "image": "python:3.11-slim", "file_ext": ".py", "cmd": ["python"]},
            "print(1)",
            timeout=5,
            memory_mb=64,
            network=False,
            use_host_fallback=True,
            workspace=tmp_path,
        )
        args = captured["args"]
        name_pos = args.index("--name")
        container = args[name_pos + 1]
        assert container.startswith("code_exec_")
        assert captured["kw"]["timeout_kill"] == ["docker", "kill", container]


class TestStoreRetention:
    def test_age_prune_removes_rows_and_artifacts(self, tmp_path) -> None:
        root = tmp_path / "artifacts"
        root.mkdir()
        store = ExecutionStore(tmp_path / "exec.db", artifact_root=root)
        store.create("old1", "python", "snippet")
        store.create("new1", "python", "snippet")
        with store._lock:
            store._conn.execute(
                "UPDATE executions SET updated_ts = ? WHERE id = 'old1'",
                (time.time() - 40 * 86400.0,),
            )
            store._conn.commit()
        (root / "old1").mkdir()
        (root / "old1" / "out.txt").write_text("stale output")
        (root / "new1").mkdir()
        purged = store.prune()
        assert purged == 1
        assert store.get("old1") is None
        assert store.get("new1") is not None
        assert not (root / "old1").exists()
        assert (root / "new1").exists()  # a live row keeps its artifacts
        store.close()

    def test_row_cap_keeps_newest(self, tmp_path) -> None:
        store = ExecutionStore(tmp_path / "exec.db")
        for i in range(205):
            store.create(f"e{i:04d}", "python", "snippet")
        # The cap is enforced lazily (sweeps are throttled to every 32nd
        # create, plus startup): one explicit prune must restore the bound
        store.prune()
        rows = store.list_recent(limit=1000)
        assert len(rows) == 200
        assert all(r["id"] != "e0000" for r in rows)  # oldest purged first
        assert rows[0]["id"] == "e0204"  # newest kept
        store.close()

    def test_orphan_artifact_sweep(self, tmp_path) -> None:
        """A crash between artifact-dir creation and row insert leaves a dir
        with no row; old orphans are removed, fresh ones (a possible run in
        flight) stay."""
        root = tmp_path / "artifacts"
        root.mkdir()
        store = ExecutionStore(tmp_path / "exec.db", artifact_root=root)
        stale = root / "orphan_stale"
        fresh = root / "orphan_fresh"
        stale.mkdir()
        fresh.mkdir()
        old = time.time() - 40 * 86400.0
        os.utime(stale, (old, old))
        store.prune()
        assert not stale.exists()
        assert fresh.exists()
        store.close()
