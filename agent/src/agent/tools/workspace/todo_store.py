"""Todo plan storage: atomic read/write of workspace/todo.json plus the plan
lifecycle operation (plan_action) shared by the todowrite tool and capability.

Follows the TodoWrite convention of mainstream harnesses: whole-list
replacement plus read-only query; three statuses pending / in_progress /
done. The list is the agent's cross-turn "current plan" — persisted so the
user can view or delete it directly. No multiple lists, no version history.

Plans are per chat session (todos/<session>.json) so parallel sessions never
overwrite each other and the UI panel follows the open session; session-less
work (REPL, background runs) shares the legacy global todo.json.
"""

from __future__ import annotations

import json
import os
import re
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

#: Session ids double as file names under workspace/todos/ — same shape the
#: gateway enforces on the chat API, re-checked here so the path can never be
#: coerced into a traversal.
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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

    def for_session(self, session: str) -> TodoStore:
        """Per-session plan store: todos/<session>.json beside the global file;
        an empty session resolves to the shared global file. The store is a
        stateless path wrapper, so deriving one per call is free."""
        sid = str(session or "").strip()
        if not sid:
            return self
        if not _SESSION_RE.fullmatch(sid):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"session 非法: {sid[:80]}",
                hint="session 取值 [A-Za-z0-9_-]{1,64}",
            )
        return TodoStore(self._path.parent / "todos" / f"{sid}.json")

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
    """The one plan-read operation: current items plus progress."""
    items = store.load()
    return {"items": items, **progress(items)}


def plan_action(
    store: TodoStore,
    *,
    action: str = "query",
    items: list[dict[str, Any]] | None = None,
    index: int | None = None,
    content: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """The one plan-mutation operation covering the whole lifecycle — set
    (whole-list replacement), query, update (patch one entry by index),
    delete (one entry by index, or clear the list without one). Raises
    ServiceError on invalid arguments; both the human capability and the
    agent's todowrite tool bind this single function — one implementation,
    two drivers, no human/agent asymmetry."""
    if action == "query":
        return read_plan(store)
    if action == "set":
        saved = store.replace(items if items is not None else [])
        return {"items": saved, **progress(saved)}
    current = store.load()
    if action == "update":
        if index is None or not (0 <= index < len(current)):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"update 需要有效 index(0-{len(current) - 1 if current else 0})",
            )
        if content is None and status is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "update 需要 content 或 status 至少其一",
            )
        entry = dict(current[index])
        if content is not None:
            entry["content"] = content
        if status is not None:
            if status not in STATUSES:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"status 非法: {status}",
                    hint="status 取值 pending / in_progress / done",
                )
            entry["status"] = status
        current[index] = entry
        saved = store.replace(current)
        return {"items": saved, **progress(saved)}
    if action == "delete":
        if index is None:
            saved = store.replace([])  # no index: clear the whole list
        else:
            if not (0 <= index < len(current)):
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"delete 需要有效 index(0-{len(current) - 1 if current else 0})",
                )
            del current[index]
            saved = store.replace(current)
        return {"items": saved, **progress(saved)}
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"action 非法: {action}",
        hint="action 取值 set / query / update / delete",
    )


__all__ = [
    "MAX_CONTENT",
    "MAX_ITEMS",
    "STATUSES",
    "TodoStore",
    "plan_action",
    "progress",
    "read_plan",
]
