"""Task graph: dependency deferral, join release, deterministic blocking on
dependency failure."""

from __future__ import annotations

from agent.master.task_graph import TaskGraph


class TestTaskGraph:
    def test_no_deps_runs_immediately(self) -> None:
        g = TaskGraph()
        assert g.pending("a", depends_on=()) == set()

    def test_already_finished_dependency_counts_as_satisfied(self) -> None:
        g = TaskGraph()
        g.finish("b", ok=True)
        assert g.pending("a", depends_on=("b",)) == set()

    def test_join_releases_when_all_finish(self) -> None:
        g = TaskGraph()
        assert g.pending("a", depends_on=("b", "c")) == {"b", "c"}
        assert g.finish("b", ok=True) == []
        releases = g.finish("c", ok=True)
        assert len(releases) == 1 and releases[0].task.name == "a" and releases[0].ok

    def test_dependency_failure_blocks_deterministically(self) -> None:
        g = TaskGraph()
        g.pending("a", depends_on=("b",))
        releases = g.finish("b", ok=False)
        assert len(releases) == 1 and releases[0].ok is False
        assert "dependency b failed" in releases[0].reason
        # 'a' is gone: it can never half-start later
        assert g.waiting_on() == {}

    def test_visibility_snapshot(self) -> None:
        g = TaskGraph()
        g.pending("a", depends_on=("b",))
        assert g.waiting_on() == {"a": ("b",)}
