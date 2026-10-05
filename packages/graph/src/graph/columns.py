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

# Plain-literal SELECT statements. The column lists mirror _NODE_COLS /
# _EDGE_COLS (which feed _row via zip) and are never widened to *.
_SQL_GET_NODE_BY_KEY = (
    "SELECT id, project, label, name, qualified_name, attrs, source, actor, updated_ts"
    " FROM nodes WHERE project=? AND label=? AND qualified_name=?"
)
_SQL_GET_NODE_BY_ID = (
    "SELECT id, project, label, name, qualified_name, attrs, source, actor, updated_ts"
    " FROM nodes WHERE project=? AND id=?"
)
_SQL_GET_EDGE_BY_ID = (
    "SELECT id, project, src, dst, type, attrs, source, actor, updated_ts FROM edges WHERE id=?"
)
_SQL_GET_EDGE_BY_PROJECT_ID = (
    "SELECT id, project, src, dst, type, attrs, source, actor, updated_ts"
    " FROM edges WHERE project=? AND id=?"
)
_SQL_EDGES_BY_PROJECT = (
    "SELECT id, project, src, dst, type, attrs, source, actor, updated_ts"
    " FROM edges WHERE project = ?"
)
_SQL_CROSS_EDGES = (
    "SELECT id, project, src, dst, type, attrs, source, actor, updated_ts"
    " FROM edges WHERE project = 'cross-repo' AND type = ?"
)


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["attrs"] = json.loads(d.get("attrs") or "{}")
    return d


def _node_row(r: tuple) -> dict[str, Any]:
    return _row(_NODE_COLS, r)


def _edge_row(r: tuple) -> dict[str, Any]:
    return _row(_EDGE_COLS, r)
