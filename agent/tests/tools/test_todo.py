"""Tests for the plan/todowrite tool: store primitives, validation, atomic
writes, the action protocol (set/query/update/delete), and per-session plan
files.
"""

import json

import pytest
from agent.tools.workspace import TodoStore, todo_tools
from platform_contracts import ErrorSuffix, ServiceError


class TestTodoStore:
    def test_missing_file_loads_empty(self, tmp_path) -> None:
        assert TodoStore(tmp_path / "todo.json").load() == []

    def test_replace_then_load_roundtrip(self, tmp_path) -> None:
        store = TodoStore(tmp_path / "todo.json")
        saved = store.replace(
            [
                {"content": "收集资料", "status": "done"},
                {"content": "写初稿"},
            ]
        )
        assert saved == [
            {"content": "收集资料", "status": "done"},
            {"content": "写初稿", "status": "pending"},  # defaults to pending
        ]
        assert TodoStore(tmp_path / "todo.json").load() == saved

    def test_replace_is_atomic_no_tmp_leftover(self, tmp_path) -> None:
        store = TodoStore(tmp_path / "todo.json")
        store.replace([{"content": "a"}])
        assert list(tmp_path.iterdir()) == [tmp_path / "todo.json"]

    def test_corrupt_file_loads_empty(self, tmp_path) -> None:
        path = tmp_path / "todo.json"
        path.write_text("{broken", encoding="utf-8")
        assert TodoStore(path).load() == []

    def test_non_list_file_loads_empty(self, tmp_path) -> None:
        path = tmp_path / "todo.json"
        path.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert TodoStore(path).load() == []

    def test_items_type_validated(self, tmp_path) -> None:
        with pytest.raises(ServiceError) as ei:
            TodoStore(tmp_path / "todo.json").replace({"content": "x"})  # type: ignore[arg-type]  # intentionally invalid: items must be a list
        assert ei.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)

    def test_empty_content_rejected(self, tmp_path) -> None:
        with pytest.raises(ServiceError) as ei:
            TodoStore(tmp_path / "todo.json").replace([{"content": "  "}])
        assert ei.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)

    def test_bad_status_rejected_with_hint(self, tmp_path) -> None:
        with pytest.raises(ServiceError) as ei:
            TodoStore(tmp_path / "todo.json").replace(
                [
                    {"content": "a", "status": "doing"},
                ]
            )
        assert ei.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        assert "pending" in ei.value.body.hint

    def test_over_long_content_truncated_not_rejected(self, tmp_path) -> None:
        saved = TodoStore(tmp_path / "todo.json").replace([{"content": "长" * 600}])
        assert len(saved[0]["content"]) == 500

    def test_item_count_boundary(self, tmp_path) -> None:
        """Exactly 100 items are within the limit; 101 are refused (guards against unbounded plan growth)."""
        store = TodoStore(tmp_path / "todo.json")
        items = [{"content": f"步骤{i}"} for i in range(100)]
        assert len(store.replace(items)) == 100
        with pytest.raises(ServiceError):
            store.replace(items + [{"content": "多一条"}])


class TestTodowriteTool:
    """One tool, one action parameter: set / query / update / delete."""

    def _tool(self, tmp_path):
        return todo_tools(TodoStore(tmp_path / "todo.json"))["todowrite"].handler

    def test_set_replaces_whole_list_and_returns_progress(self, tmp_path) -> None:
        out = self._tool(tmp_path)(
            action="set",
            items=[{"content": "a", "status": "done"}, {"content": "b"}],
        )
        assert out == {
            "items": [
                {"content": "a", "status": "done"},
                {"content": "b", "status": "pending"},
            ],
            "done": 1,
            "total": 2,
        }

    def test_query_returns_current_plan(self, tmp_path) -> None:
        tool = self._tool(tmp_path)
        tool(action="set", items=[{"content": "步骤一"}])
        out = tool(action="query")
        assert out["items"] == [{"content": "步骤一", "status": "pending"}]
        assert out["total"] == 1 and out["done"] == 0

    def test_query_empty(self, tmp_path) -> None:
        assert self._tool(tmp_path)(action="query") == {"items": [], "done": 0, "total": 0}

    def test_update_patches_one_entry(self, tmp_path) -> None:
        tool = self._tool(tmp_path)
        tool(action="set", items=[{"content": "a"}, {"content": "b"}])
        out = tool(action="update", index=0, status="done")
        assert out["items"][0] == {"content": "a", "status": "done"}
        assert out["done"] == 1
        out = tool(action="update", index=1, content="b2")
        assert out["items"][1] == {"content": "b2", "status": "pending"}

    def test_update_index_bounds_and_missing_fields(self, tmp_path) -> None:
        tool = self._tool(tmp_path)
        assert "[参数错误]" in tool(action="update", index=0, status="done")
        tool(action="set", items=[{"content": "a"}])
        assert "[参数错误]" in tool(action="update", index=5, status="done")
        assert "[参数错误]" in tool(action="update", index=0)

    def test_delete_removes_one_entry_or_clears(self, tmp_path) -> None:
        tool = self._tool(tmp_path)
        tool(action="set", items=[{"content": "a"}, {"content": "b"}])
        out = tool(action="delete", index=0)
        assert [it["content"] for it in out["items"]] == ["b"]
        out = tool(action="delete")  # no index: clear the whole list
        assert out == {"items": [], "done": 0, "total": 0}

    def test_delete_index_bounds(self, tmp_path) -> None:
        tool = self._tool(tmp_path)
        assert "[参数错误]" in tool(action="delete", index=0)
        tool(action="set", items=[{"content": "a"}])
        assert "[参数错误]" in tool(action="delete", index=5)

    def test_unknown_action_reports(self, tmp_path) -> None:
        assert "[参数错误]" in self._tool(tmp_path)(action="upsert")

    def test_write_flag_blocks_retry(self, tmp_path) -> None:
        """todowrite is a write tool: writes are never retried (the invoke layer checks the write flag)."""
        tool = todo_tools(TodoStore(tmp_path / "todo.json"))["todowrite"]
        assert tool.write is True

    def test_status_whitespace_and_case(self, tmp_path) -> None:
        """Status values are not normalized for whitespace or case: strict matching prevents silent semantic drift."""
        store = TodoStore(tmp_path / "todo.json")
        saved = store.replace([{"content": "a", "status": "done"}])
        assert saved[0]["status"] == "done"
        with pytest.raises(ServiceError):
            store.replace([{"content": "a", "status": " DONE "}])
        self._tool(tmp_path)(action="query")


class TestSessionPlans:
    """Plans are per chat session: todos/<session>.json beside the global file;
    session-less work keeps using the shared todo.json."""

    def _tool(self, tmp_path):
        return todo_tools(TodoStore(tmp_path / "todo.json"))["todowrite"].handler

    def test_empty_session_resolves_to_global(self, tmp_path) -> None:
        store = TodoStore(tmp_path / "todo.json")
        assert store.for_session("") is store
        assert store.for_session("  ") is store

    def test_session_store_path_and_isolation(self, tmp_path) -> None:
        store = TodoStore(tmp_path / "todo.json")
        plan = store.for_session("sess-a")
        assert plan._path == tmp_path / "todos" / "sess-a.json"
        plan.replace([{"content": "会话计划"}])
        store.replace([{"content": "全局计划"}])
        assert plan.load() == [{"content": "会话计划", "status": "pending"}]
        assert store.load() == [{"content": "全局计划", "status": "pending"}]
        assert store.for_session("sess-b").load() == []

    def test_illegal_session_rejected(self, tmp_path) -> None:
        """Session ids become file names: same shape the gateway enforces,
        re-checked here so the path can never be coerced into a traversal."""
        store = TodoStore(tmp_path / "todo.json")
        for bad in ("../evil", "a/b", "a b", ".", "x" * 65, "会话"):
            with pytest.raises(ServiceError) as ei:
                store.for_session(bad)
            assert ei.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)

    def test_tools_without_turn_write_global(self, tmp_path) -> None:
        """No executing instance in the context: the tools keep the legacy
        global-file behavior (REPL / background runs)."""
        tool = self._tool(tmp_path)
        tool(action="set", items=[{"content": "全局"}])
        assert (tmp_path / "todo.json").exists()
        assert not (tmp_path / "todos").exists()

    def test_tools_follow_current_session(self, tmp_path) -> None:
        from types import SimpleNamespace

        from agent.runtime.current import current_instance

        tool = self._tool(tmp_path)
        token = current_instance.set(SimpleNamespace(task=SimpleNamespace(session="sess-a")))
        try:
            tool(action="set", items=[{"content": "会话内"}])
            assert tool(action="query")["items"] == [{"content": "会话内", "status": "pending"}]
        finally:
            current_instance.reset(token)
        # The global file stays untouched by the session-scoped write
        assert TodoStore(tmp_path / "todo.json").load() == []
