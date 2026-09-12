"""Tests for the plan/todo tools: store primitives, validation, atomic writes,
and tool handlers.
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

    def test_non_dict_item_rejected(self, tmp_path) -> None:
        with pytest.raises(ServiceError):
            TodoStore(tmp_path / "todo.json").replace(["a"])  # type: ignore[list-item]  # intentionally invalid: items must be dicts

    def test_over_long_content_truncated_not_rejected(self, tmp_path) -> None:
        saved = TodoStore(tmp_path / "todo.json").replace([{"content": "长" * 600}])
        assert len(saved[0]["content"]) == 500


class TestTodoTools:
    def _tools(self, tmp_path):
        return todo_tools(TodoStore(tmp_path / "todo.json"))

    def test_write_returns_progress(self, tmp_path) -> None:
        out = self._tools(tmp_path)["todo_write"].handler(
            [
                {"content": "a", "status": "done"},
                {"content": "b"},
            ]
        )
        assert out == {
            "items": [
                {"content": "a", "status": "done"},
                {"content": "b", "status": "pending"},
            ],
            "done": 1,
            "total": 2,
        }

    def test_read_reflects_write(self, tmp_path) -> None:
        tools = self._tools(tmp_path)
        tools["todo_write"].handler([{"content": "步骤一"}])
        out = tools["todo_read"].handler()
        assert out["items"] == [{"content": "步骤一", "status": "pending"}]
        assert out["total"] == 1 and out["done"] == 0

    def test_read_empty(self, tmp_path) -> None:
        out = self._tools(tmp_path)["todo_read"].handler()
        assert out == {"items": [], "done": 0, "total": 0}

    def test_write_flag_blocks_retry(self, tmp_path) -> None:
        """todo_write is a write tool: writes are never retried (the invoke layer checks the write flag)."""
        assert self._tools(tmp_path)["todo_write"].write is True

    def test_item_count_boundary(self, tmp_path) -> None:
        """Exactly 100 items are within the limit; 101 are refused (guards against unbounded plan growth)."""
        store = TodoStore(tmp_path / "todo.json")
        items = [{"content": f"步骤{i}"} for i in range(100)]
        assert len(store.replace(items)) == 100
        with pytest.raises(ServiceError):
            store.replace(items + [{"content": "多一条"}])

    def test_empty_replace_clears_file(self, tmp_path) -> None:
        """Replacing with an empty list clears the plan (valid semantics; no stale file content lingers)."""
        store = TodoStore(tmp_path / "todo.json")
        store.replace([{"content": "a"}])
        assert store.replace([]) == []
        assert store.load() == []

    def test_status_whitespace_and_case(self, tmp_path) -> None:
        """Status values are not normalized for whitespace or case: strict matching prevents silent semantic drift."""
        store = TodoStore(tmp_path / "todo.json")
        saved = store.replace([{"content": "a", "status": "done"}])
        assert saved[0]["status"] == "done"
        with pytest.raises(ServiceError):
            store.replace([{"content": "a", "status": " DONE "}])
