"""AI pipeline: agents build the graph directly via
set_node/set_relationship.

This module holds the graph-building conventions and validation for agents
(it is not an executor):
- Label/type vocabularies (open set; the list is a recommendation, not a block);
- Validation of required fields, name length, non-empty project;
- guide_text(): graph-building guidance injected into agent context,
  loaded on demand.
"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "graph"

#: Recommended labels (open set): common concept layer for book/news/doc graphs
RECOMMENDED_LABELS = (
    "Concept",
    "Topic",
    "Person",
    "Organization",
    "Book",
    "Chapter",
    "Article",
    "Event",
    "Term",
    "Project",
    "File",
    "Function",
    "Class",
)

RECOMMENDED_RELATIONS = (
    "CONTAINS",
    "RELATES_TO",
    "DEPENDS_ON",
    "EXPLAINS",
    "MENTIONS",
    "AUTHORED_BY",
    "PART_OF",
    "COMPARED_WITH",
    "CALLS",
    "IMPORTS",
)

_GUIDE = """# AI 建图约定(§8.4)

- 节点:set_node(project, label, name, qualified_name?, attrs?)
  —— upsert 语义,同一 (project, label, qualified_name) 重复写=更新;
- 关系:set_relationship(project, src_qualified_name, dst_qualified_name, type, attrs?)
  —— 两端节点不存在时自动补占位节点(label=Term);
- project 即资源 id(仓库/书籍/新闻);同一资源的所有内容进同一 project 图;
- 推荐标签:Concept/Topic/Chapter/Article/Term…;推荐关系:CONTAINS/EXPLAINS/MENTIONS…;
  词表是推荐不是封锁,新概念类型允许,但保持一致(大写蛇形);
- 批量建图:先建骨架(章→节),再填概念与关系;每条调用都带来源摘录进 attrs.quote。
"""


def validate_nodes_batch(project: str, nodes: list[dict]) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project must not be empty")
    for i, n in enumerate(nodes):
        validate_node(project, n.get("label", ""), n.get("name", ""))


def validate_relations_batch(project: str, relations: list[dict]) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project must not be empty")
    for i, r in enumerate(relations):
        validate_relation(project, r.get("src", ""), r.get("dst", ""), r.get("type", ""))


def guide_text() -> str:
    return _GUIDE


def validate_node(project: str, label: str, name: str) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project must not be empty")
    if not label.strip():
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "label must not be empty",
            hint=f"recommended: {', '.join(RECOMMENDED_LABELS[:6])}…",
        )
    if not name.strip() or len(name) > 200:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "name is required and must be at most 200 characters",
        )


def validate_relation(project: str, src: str, dst: str, type_: str) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project must not be empty")
    if not src.strip() or not dst.strip():
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "src/dst are node qualified_names and must not be empty",
        )
    if not type_.strip():
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "relationship type must not be empty",
            hint=f"recommended: {', '.join(RECOMMENDED_RELATIONS[:6])}…",
        )
