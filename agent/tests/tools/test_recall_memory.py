"""Tests for the recall_memory one-shot request bound."""

from agent.tools.memory.recall_memory import recall_memory_tool


class _Loader:
    def __init__(self) -> None:
        self.seen: list[int] = []

    def recall(self, query: str, limit: int) -> list:
        self.seen.append(limit)
        return []


class TestRecallLimitBound:
    def test_default_limit(self) -> None:
        loader = _Loader()
        recall_memory_tool(loader).handler("什么偏好?")
        assert loader.seen == [8]

    def test_oversized_limit_clamped(self) -> None:
        loader = _Loader()
        recall_memory_tool(loader).handler("什么偏好?", limit=100)
        assert loader.seen == [20]

    def test_nonpositive_limit_raises_to_one(self) -> None:
        loader = _Loader()
        tool = recall_memory_tool(loader)
        tool.handler("什么偏好?", limit=0)
        tool.handler("什么偏好?", limit=-3)
        assert loader.seen == [1, 1]

    def test_null_or_wrong_type_falls_back_to_default(self) -> None:
        loader = _Loader()
        tool = recall_memory_tool(loader)
        tool.handler("什么偏好?", limit=None)  # type: ignore[arg-type]
        tool.handler("什么偏好?", limit=True)  # type: ignore[arg-type]
        assert loader.seen == [8, 8]
