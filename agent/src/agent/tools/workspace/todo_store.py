"""Todo plan storage: atomic read/write of workspace/todo.json plus the one
read-projection (read_plan) shared by the todo_read tool and capability.

Follows the TodoWrite convention of mainstream harnesses: whole-list
replacement plus read-only query; three statuses pending / in_progress /
done. The list is the agent's cross-turn "current plan" — persisted so the
user can view or delete it directly. No multiple lists, no version history.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

#: The three statuses
STATUSES = ("pending", "in_progress", "done")
_STATUS = frozenset(STATUSES)

#: Cap on list length and per-item content length (keeps the list from
#: bloating and crowding the context)
MAX_ITEMS = 100
MAX_CONTENT = 500


def _normalize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize a whole list: content required and non-empty,
    status narrowed to the three values (default pending)."""
    if not isinstance(items, list):
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            "items 必须是数组",
            hint=f"每次整表替换,至多 {MAX_ITEMS} 条",
        )
    if len(items) > MAX_ITEMS:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"条目数 {len(items)} 超上限 {MAX_ITEMS}",
        )
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"第 {i} 条必须是对象",
            )
        content = str(item.get("content", "")).strip()
        if not content:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"第 {i} 条 content 不能为空",
            )
        if len(content) > MAX_CONTENT:
            content = content[:MAX_CONTENT]
        status = str(item.get("status") or "pending")
        if status not in _STATUS:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"第 {i} 条 status 非法: {status}",
                hint="status 取值 pending / in_progress / done",
            )
        out.append({"content": content, "status": status})
    return out


class TodoStore:
    """Atomic read/write of todo.json; single file, single responsibility,
    unaware of the tool layer."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> list[dict[str, Any]]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError:
            return []  # unreadable counts as empty: the list is auxiliary, not worth blocking
        try:
            items = json.loads(raw)
        except ValueError:
            return []  # corrupt file counts as empty; the next todo_write overwrites and rebuilds
        return items if isinstance(items, list) else []

    def replace(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace the whole list and persist it; returns the normalized list."""
        norm = _normalize(items)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write (same discipline as CheckpointStore): temp file + os.replace into place
        tmp = self._path.with_name(f".{self._path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        return norm


def progress(items: list[dict[str, Any]]) -> dict[str, int]:
    done = sum(1 for it in items if it.get("status") == "done")
    return {"done": done, "total": len(items)}


def read_plan(store: TodoStore) -> dict[str, Any]:
    """The one todo-read operation: current items plus progress. Both the LLM
    tool binding (todo_read) and the human capability binding (todo_read) call
    this single function — written once, same name on both surfaces."""
    items = store.load()
    return {"items": items, **progress(items)}


__all__ = ["MAX_CONTENT", "MAX_ITEMS", "STATUSES", "TodoStore", "progress", "read_plan"]
