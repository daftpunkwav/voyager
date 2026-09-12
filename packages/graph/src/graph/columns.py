"""Column constants for the nodes/edges tables plus row-to-dict
helpers.

Shared by store and operations to avoid circular imports.
"""

from __future__ import annotations

import json
from typing import Any

_NODE_COLS = (
    "id",
    "project",
    "label",
    "name",
    "qualified_name",
    "attrs",
    "source",
    "actor",
    "updated_ts",
)
_EDGE_COLS = ("id", "project", "src", "dst", "type", "attrs", "source", "actor", "updated_ts")


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["attrs"] = json.loads(d.get("attrs") or "{}")
    return d


def _node_row(r: tuple) -> dict[str, Any]:
    return _row(_NODE_COLS, r)


def _edge_row(r: tuple) -> dict[str, Any]:
    return _row(_EDGE_COLS, r)
