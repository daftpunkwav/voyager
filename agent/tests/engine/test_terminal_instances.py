"""Spawner terminal-instance residency: only terminal instances count
against the cap and the oldest are evicted; alive and queued runs stay."""

import pytest
from agent.engine.instance import TaskBook
from agent.engine.spawn import TERMINAL_INSTANCE_CAP
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime.state import RunStatus


class TestTerminalInstanceCap:
    """Spawner terminal-instance residency cap: only terminal instances are evicted; alive/PENDING ones stay."""

    @staticmethod
    def _spawn_many(app, n: int, *, status: RunStatus) -> list:
        insts = []
        for i in range(n):
            inst = app.spawner.spawn(TaskBook(goal=f"task{i}"))
            inst.state.status = status
            insts.append(inst)
        return insts

    def test_trim_evicts_oldest_terminal_keeps_alive(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            alive = self._spawn_many(app, 2, status=RunStatus.RUNNING)
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP + 2, status=RunStatus.COMPLETED)
            evicted = app.spawner._trim_terminal_instances()
            assert evicted == [
                i.id for i in terminal[:2]
            ]  # oldest by insertion order evicted first
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP + len(alive)
            assert all(
                i.id in app.spawner.instances for i in alive
            )  # alive instances are never evicted
            assert terminal[-1].id in app.spawner.instances  # newest terminal instance kept
        finally:
            app.memory.close()

    def test_trim_deletes_evicted_checkpoint_files(self, tmp_path) -> None:
        """Eviction is semantic termination: the evicted run's checkpoint file
        is deleted, not just the in-memory registry entry."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP + 1, status=RunStatus.COMPLETED)
            for inst in terminal:
                app.checkpoints.save(inst.state)
            evicted = app.spawner._trim_terminal_instances()
            assert len(evicted) == 1
            with pytest.raises(FileNotFoundError):
                app.checkpoints.load(evicted[0])
            kept = terminal[-1]  # newest terminal instance stays, checkpoint intact
            assert app.checkpoints.load(kept.state.run_id).run_id == kept.state.run_id
        finally:
            app.memory.close()

    def test_trim_never_touches_pending_or_alive(self, tmp_path) -> None:
        """PENDING instances have not run yet in the scheduler queue and do not count as terminal."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            self._spawn_many(app, 40, status=RunStatus.PENDING)
            alive = self._spawn_many(app, 5, status=RunStatus.WAITING_INPUT)
            assert app.spawner._trim_terminal_instances() == []
            assert len(app.spawner.instances) == 45
            assert all(i.id in app.spawner.instances for i in alive)
        finally:
            app.memory.close()

    async def test_cancel_triggers_trim(self, tmp_path) -> None:
        """Trigger point: once a cancel lands CANCELLED and the cap is exceeded, the oldest terminal instance is evicted."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP, status=RunStatus.COMPLETED)
            (stop,) = self._spawn_many(app, 1, status=RunStatus.RUNNING)
            cancelled = await app.spawner.cancel(stop.id)
            assert cancelled == [stop.id]
            # 33 terminal > 32 cap: the oldest one is evicted
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP
            assert terminal[0].id not in app.spawner.instances
            assert terminal[-1].id in app.spawner.instances
        finally:
            app.memory.close()
