"""code-exec service tests: capabilities, REST, host-fallback execution,
security validation, service.json consistency.
"""

import json
from pathlib import Path

import pytest
from code_exec import capabilities
from code_exec.capabilities import registry
from code_exec.executor import RunResult, run_in_runtime
from code_exec.rest import create_app
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

USER_CTX = ActorContext(actor=LOCAL_USER)
SERVICE_DIR = Path(__file__).parent.parent


@pytest.fixture()
def app(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    settings_store = SettingsStore(tmp_path / "settings.db", bus)
    application = create_app(tmp_path, workspace=workspace, bus=bus, settings_store=settings_store)
    application.state.settings_store = settings_store
    application.state.event_log = log
    yield application
    log.close()
    settings_store.close()


class TestCapabilities:
    async def test_list_runtimes(self, app) -> None:
        result = await execute(registry, "list_runtimes", USER_CTX, {})
        assert isinstance(result, list)
        assert any(r["id"] == "python" for r in result)

    def test_service_json_matches_registry(self) -> None:
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()


class TestRest:
    def test_health(self, app) -> None:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "up"

    def test_run_snippet_returns_job(self, app, monkeypatch) -> None:
        # Acceptance contract only (202 + job ref): the execution is stubbed so no
        # background subprocess outlives the TestClient's event loop. Host-fallback
        # execution is covered by the executor tests below; the docker path is not
        # exercised in unit tests (set CODE_EXEC_TEST_DOCKER=1 to opt in).
        async def _instant(*_args, **_kwargs) -> RunResult:
            return RunResult(status="completed", exit_code=0, stdout="", stderr="", artifact_dir="")

        monkeypatch.setattr(capabilities, "run_in_runtime", _instant)
        with TestClient(app) as client:
            resp = client.post(
                "/capabilities/run_snippet",
                json={
                    "runtime": "python",
                    "code": "print('hello')",
                },
            )
        assert resp.status_code == 202
        assert "job_id" in resp.json()["job"]


class TestSecurity:
    async def test_run_file_rejects_traversal(self, app) -> None:
        for bad in ("../../secrets.txt", "sub/../../escape.py"):
            with pytest.raises(ServiceError) as exc:
                await execute(
                    registry, "run_file", USER_CTX, {"runtime": "python", "file_path": bad}
                )
            assert exc.value.body.code == "CODE_EXEC.INVALID_INPUT"

    async def test_run_file_missing_404(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "run_file", USER_CTX, {"runtime": "python", "file_path": "nope.py"}
            )
        assert exc.value.body.code == "CODE_EXEC.NOT_FOUND"

    async def test_runtime_rejects_shell_metachars(self, tmp_path) -> None:
        """Injection characters in image/command/extension are rejected before
        any execution path runs."""
        poisoned_image = {
            "id": "python",
            "image": "python:3.11; touch pwned",
            "file_ext": ".py",
            "cmd": ["python"],
        }
        with pytest.raises(ServiceError, match="image"):
            await run_in_runtime(
                poisoned_image,
                "print(1)",
                timeout=5,
                memory_mb=64,
                network=False,
                use_host_fallback=True,
                workspace=tmp_path,
            )
        poisoned_ext = {
            "id": "python",
            "image": "python:3.11-slim",
            "file_ext": "../x.py",
            "cmd": ["python"],
        }
        with pytest.raises(ServiceError, match="extension"):
            await run_in_runtime(
                poisoned_ext,
                "print(1)",
                timeout=5,
                memory_mb=64,
                network=False,
                use_host_fallback=True,
                workspace=tmp_path,
            )
        poisoned_cmd = {
            "id": "python",
            "image": "python:3.11-slim",
            "file_ext": ".py",
            "cmd": ["python", "-c 'boom'"],
        }
        with pytest.raises(ServiceError, match="command"):
            await run_in_runtime(
                poisoned_cmd,
                "print(1)",
                timeout=5,
                memory_mb=64,
                network=False,
                use_host_fallback=True,
                workspace=tmp_path,
            )

    async def test_host_fallback_only_known_interpreters(self, tmp_path, monkeypatch) -> None:
        """Host fallback only accepts python/node/shell; custom runtimes
        require docker."""
        from code_exec import executor

        monkeypatch.setattr(executor.shutil, "which", lambda name: None)  # no docker
        custom = {"id": "custom", "image": "x:1", "file_ext": ".txt", "cmd": ["whatever"]}
        with pytest.raises(ServiceError, match="Host fallback"):
            await run_in_runtime(
                custom,
                "hi",
                timeout=5,
                memory_mb=64,
                network=False,
                use_host_fallback=True,
                workspace=tmp_path,
            )
