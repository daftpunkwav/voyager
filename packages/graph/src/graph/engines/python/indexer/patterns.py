"""Scan regexes for all languages (single source of truth; language
modules reference these).
"""

from __future__ import annotations

import re

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MD_SETEXT_RE = re.compile(r"^(.+)\n(=+|-+)\s*$", re.MULTILINE)
JS_INTERFACE_RE = re.compile(
    r"(?:export\s+)?interface\s+([A-Za-z_][\w$]*)",
)
JS_TYPE_RE = re.compile(
    r"(?:export\s+)?type\s+([A-Za-z_][\w$]*)\s*=",
)
JS_CLASS_RE = re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_][\w$]*)")
JS_FN_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_][\w$]*)\s*\(",
)
JS_ARROW_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_][\w$]*)\s*=>",
)
JS_VAR_RE = re.compile(
    # Top-level declarations only = module scope (aligned with the native engine's
    # Variable, avoids an explosion of nested consts)
    r"(?m)^(export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=",
)
JS_METHOD_RE = re.compile(
    # Indented methods inside class bodies (heuristic, matches the native engine's Method volume)
    r"(?m)^[ \t]{2,8}(?:async\s+)?(?:static\s+)?(?:async\s+)?(?:get|set\s+)?([A-Za-z_][\w$]*)\s*\([^)]*\)\s*\{",
)
JS_IMPORT_RE = re.compile(
    r"""(?:from\s+['"]([^'"]+)['"]|import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))"""
)
GO_FN_RE = re.compile(r"func\s+(?:\([^)]+\)\s*)?([A-Za-z_][\w]*)\s*\(")
GO_TYPE_RE = re.compile(r"type\s+([A-Za-z_][\w]*)\s+(?:struct|interface|func|=)")
RS_FN_RE = re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*[<(]")
RS_STRUCT_RE = re.compile(r"(?:pub\s+)?(?:struct|enum|trait|type)\s+([A-Za-z_][\w]*)")
JAVA_CLASS_RE = re.compile(
    r"(?:public|protected|private|abstract|final|\s)*\s*(?:class|interface|enum|record)\s+([A-Za-z_][\w]*)"
)
JAVA_FN_RE = re.compile(
    r"(?:public|private|protected|static|\s)+\s+[\w<>\[\]]+\s+([A-Za-z_][\w]*)\s*\("
)
CALL_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s*\(")
PY_ROUTE_RE = re.compile(
    r"""@(?:\w+\.)?(?:get|post|put|patch|delete|route|api_route|head|options)\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
JS_ROUTE_RE = re.compile(
    r"""(?:\.(?:get|post|put|patch|delete|use|all)|router\.(?:get|post|put|patch|delete|use))\(\s*['"`]([^'"`]+)['"`]""",
    re.IGNORECASE,
)
ENV_ASSIGN_RE = re.compile(
    r"""(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,64})\s*=\s*["']?([^\s#'"]+)"""
)
ENV_USAGE_RE = re.compile(
    r"""(?:os\.environ(?:\.get)?|os\.getenv|process\.env)\[['\"]([A-Z][A-Z0-9_]{1,64})['\"]\]|"""
    r"""(?:os\.environ\.get|os\.getenv)\(\s*['\"]([A-Z][A-Z0-9_]{1,64})['\"]"""
    r"""|process\.env\.([A-Z][A-Z0-9_]{1,64})"""
)
DECORATOR_NAME_RE = re.compile(r"^@([\w\.]+)")
