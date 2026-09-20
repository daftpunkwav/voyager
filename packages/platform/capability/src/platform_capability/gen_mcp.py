"""Registry to MCP server (one of the two generated protocols).

The MCP SDK is an optional dependency (extra `mcp`) imported only when
build_server is called. build_tool_specs and dataclass_to_json_schema are
pure functions usable without the SDK (reused by REST capability listing).
OAuth 2.1 issuance for external clients is a future step; default_actor
currently defaults to the local user.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import types
import typing
from collections.abc import Iterable
from typing import Any

from platform_contracts import LOCAL_USER, ActorRef

from platform_capability.define import Capability
from platform_capability.registry import Registry

_PRIMITIVE_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}
_UNION_ORIGINS = {typing.Union, types.UnionType}  # Optional[X] and X | None


def _unwrap_optional(expected: Any) -> Any:
    """Optional[X] / X | None -> X; anything else is returned as-is."""
    if typing.get_origin(expected) in _UNION_ORIGINS:
        args = [a for a in typing.get_args(expected) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return expected


def dataclass_to_json_schema(model: type) -> dict[str, Any]:
    """dataclass to JSON Schema (shallow: primitives mapped, composite types
    marked object/array, everything else any)."""
    hints = typing.get_type_hints(model)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(model):
        expected = _unwrap_optional(hints.get(f.name))
        origin = typing.get_origin(expected)
        if expected in _PRIMITIVE_JSON:
            schema: dict[str, Any] = {"type": _PRIMITIVE_JSON[expected]}
        elif expected is list or origin is list:
            schema = {"type": "array"}
        elif expected is dict or origin is dict:
            schema = {"type": "object"}
        else:
            schema = {}
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
        elif f.default is not dataclasses.MISSING:
            schema["default"] = f.default
        properties[f.name] = schema
    return {"type": "object", "properties": properties, "required": required}


def _annotation_to_schema(expected: Any, default: Any = inspect.Parameter.empty) -> dict[str, Any]:
    """One handler parameter annotation -> JSON schema fragment (same shallow
    mapping as the dataclass path; list items typed when primitively hinted)."""
    expected = _unwrap_optional(expected)
    origin = typing.get_origin(expected)
    if expected in _PRIMITIVE_JSON:
        schema: dict[str, Any] = {"type": _PRIMITIVE_JSON[expected]}
    elif expected is list or origin is list:
        schema = {"type": "array"}
        args = typing.get_args(expected)
        if len(args) == 1 and args[0] in _PRIMITIVE_JSON:
            schema["items"] = {"type": _PRIMITIVE_JSON[args[0]]}
    elif expected is dict or origin is dict:
        schema = {"type": "object"}
    else:
        schema = {}
    if default is not inspect.Parameter.empty and default is not None:
        schema["default"] = default
    return schema


def capability_input_schema(cap: Capability) -> dict[str, Any]:
    """Input schema for a capability: the dataclass model when declared, else
    derived from the handler signature.

    The signature fallback matters: an unmodeled capability used to expose an
    empty schema, leaving LLM/MCP/REST consumers to guess argument names —
    which surfaced as TypeError loops when the agent called such tools. Params
    without annotations map to "any"; *args/**kwargs are skipped. The `_actor`
    parameter is also skipped: execute() injects it from the caller's
    ActorContext, so publishing it would invite callers to pass it (a
    duplicate-keyword TypeError) and leak harness plumbing into tool schemas.
    """
    if cap.input_model is not None:
        return dataclass_to_json_schema(cap.input_model)
    try:
        hints = typing.get_type_hints(cap.handler)
    except (NameError, AttributeError, TypeError):
        # Unresolvable forward refs / exotic annotations: params fall back to "any"
        hints = {}
    params: Iterable[inspect.Parameter]
    try:
        params = inspect.signature(cap.handler).parameters.values()
    except (TypeError, ValueError):
        params = ()
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in params:
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.name == "_actor":  # execute()-injected; never caller-supplied
            continue
        properties[param.name] = _annotation_to_schema(hints.get(param.name), param.default)
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    return {"type": "object", "properties": properties, "required": required}


def build_tool_specs(registry: Registry) -> list[dict[str, Any]]:
    """Tool descriptions for MCP tools/list (pure function)."""
    return [
        {
            "name": cap.name,
            "description": cap.description,
            "inputSchema": capability_input_schema(cap),
        }
        for cap in registry.all()
    ]


def build_server(
    registry: Registry,
    *,
    name: str = "capability-server",
    default_actor: ActorRef = LOCAL_USER,
    auth: list | None = None,
    quota: list | None = None,
    audit: list | None = None,
):
    """Generate an MCP server from the registry (low-level Server, explicit
    schemas). Raises RuntimeError when the SDK is missing."""
    try:
        from mcp.server import Server
        from mcp.types import ErrorData, McpError, TextContent, Tool
    except ImportError as exc:
        raise RuntimeError("build_server requires the MCP SDK: pip install 'mcp>=1.0'") from exc

    from platform_actor import ActorContext
    from platform_contracts import ServiceError

    from platform_capability.guards import execute

    server: Any = Server(name)

    @server.list_tools()
    async def _list_tools() -> list:
        return [
            Tool(
                name=spec["name"],
                description=spec["description"],
                inputSchema=spec["inputSchema"],
            )
            for spec in build_tool_specs(registry)
        ]

    @server.call_tool()
    async def _call_tool(tool_name: str, arguments: dict) -> list:
        try:
            result = await execute(
                registry,
                tool_name,
                ActorContext(actor=default_actor),
                arguments or {},
                auth=auth,
                quota=quota,
                audit=audit,
            )
        except ServiceError as exc:
            raise McpError(
                ErrorData(code=-32000, message=json.dumps(exc.to_envelope(), ensure_ascii=False))
            ) from exc
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            result = dataclasses.asdict(result)
        elif hasattr(result, "to_dict"):
            result = result.to_dict()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server
