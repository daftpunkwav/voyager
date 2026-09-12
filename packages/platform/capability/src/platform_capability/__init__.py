"""Capability framework: define once, generate REST + MCP; enforced
auth/quota/audit at the entry point.
"""

from platform_capability.audit_db import SqliteAuditSink
from platform_capability.define import Capability, capability, coerce_input
from platform_capability.gen_mcp import (
    build_server,
    build_tool_specs,
    capability_input_schema,
    dataclass_to_json_schema,
)
from platform_capability.gen_rest import build_router
from platform_capability.guards import (
    SENSITIVE_KEYS,
    AuditEntry,
    AuditSink,
    CallRequest,
    CostQuota,
    InMemoryAuditSink,
    LocalAuth,
    execute,
    summarize_args,
)
from platform_capability.registry import Registry
from platform_capability.wiring import Wiring

__all__ = [
    "SENSITIVE_KEYS",
    "AuditEntry",
    "AuditSink",
    "CallRequest",
    "Capability",
    "CostQuota",
    "InMemoryAuditSink",
    "LocalAuth",
    "Registry",
    "SqliteAuditSink",
    "Wiring",
    "build_router",
    "build_server",
    "build_tool_specs",
    "capability",
    "capability_input_schema",
    "coerce_input",
    "dataclass_to_json_schema",
    "execute",
    "summarize_args",
]
