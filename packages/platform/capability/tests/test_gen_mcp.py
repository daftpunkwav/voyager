"""Tests for MCP generation: JSON Schema derivation, tool specs (pure
functions), and the generated MCP server (exercised through a stub SDK —
the real `mcp` package is an optional dependency).
"""

from dataclasses import dataclass
from typing import Any

import pytest
from platform_capability import Registry, build_tool_specs, capability, dataclass_to_json_schema


@dataclass
class _In:
    text: str
    count: int = 3
    ratio: float = 0.5
    flag: bool = False
    tags: list | None = None
    meta: dict | None = None


@dataclass
class _Nested:
    """A field type outside the shallow primitive/array/object mapping."""

    inner: int = 0
    when: Any = None


class TestJsonSchema:
    def test_primitive_mapping(self) -> None:
        schema = dataclass_to_json_schema(_In)
        props = schema["properties"]
        assert props["text"] == {"type": "string"}
        assert props["count"] == {"type": "integer", "default": 3}
        assert props["ratio"]["type"] == "number"
        assert props["flag"]["type"] == "boolean"
        assert props["tags"]["type"] == "array"
        assert props["meta"]["type"] == "object"

    def test_required_only_for_no_default(self) -> None:
        assert dataclass_to_json_schema(_In)["required"] == ["text"]


class TestToolSpecs:
    def test_specs_shape(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="echo", description="echo text", input_model=_In)
        def echo(data: _In) -> dict:
            return {}

        @capability(reg, name="ping", description="no inputs")
        def ping() -> dict:
            return {}

        specs = build_tool_specs(reg)
        assert [s["name"] for s in specs] == ["echo", "ping"]
        assert specs[0]["inputSchema"]["properties"]["text"] == {"type": "string"}
        assert specs[1]["inputSchema"] == {
            "type": "object",
            "properties": {},
            "required": [],
        }


class TestSignatureSchema:
    """Unmodeled capabilities derive their input schema from the handler
    signature: an empty schema used to leave LLM/MCP consumers guessing
    argument names (agent-side TypeError loops)."""

    async def test_unmodeled_handler_schema_from_signature(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="create_note", description="create")
        async def create_note(title: str, content: str = "", tags: list[str] | None = None) -> dict:
            return {}

        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert schema["properties"]["title"] == {"type": "string"}
        assert schema["properties"]["content"] == {"type": "string", "default": ""}
        # list[str] keeps its item typing; None default emits no "default" key
        assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
        assert schema["required"] == ["title"]

    async def test_varargs_skipped_and_unannotated_params_typed_string(self) -> None:
        """Unannotated params fall back to a permissive string: providers
        validate tool schemas strictly and reject a property with no `type`
        (MiniMax's anthropic layer answers a bare 400 InvalidParameter)."""
        reg = Registry("misc")

        @capability(reg, name="flex", description="flexible")
        def flex(a, *args, extra: dict | None = None, **kwargs) -> dict:
            return {}

        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert set(schema["properties"]) == {"a", "extra"}
        assert schema["properties"]["a"] == {"type": "string"}
        assert schema["properties"]["extra"] == {"type": "object"}

    async def test_actor_param_is_not_published(self) -> None:
        """`_actor` is injected by execute() from the caller's ActorContext:
        publishing it in the schema would invite callers to pass it (a
        duplicate-keyword TypeError) and leak harness plumbing into tool
        schemas."""
        from platform_contracts import ActorRef

        reg = Registry("goal")

        @capability(reg, name="goal", description="durable goal")
        def goal(
            action: str,
            scope: str = "main",
            _actor: ActorRef | None = None,
        ) -> dict:
            return {}

        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert set(schema["properties"]) == {"action", "scope"}
        assert schema["required"] == ["action"]

    async def test_tool_surface_prefers_input_model(self) -> None:
        reg = Registry("both")

        @capability(reg, name="modeled", description="model wins", input_model=_In)
        def modeled(data: _In) -> dict:
            return {}

        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert schema["properties"]["text"] == {
            "type": "string"
        }  # dataclass shape, not the handler's param
        assert schema["required"] == ["text"]

    def test_composite_types_fall_back_to_permissive_empty_schema(self) -> None:
        """Field types outside the shallow primitive/array/object mapping
        (e.g. Any, nested dataclasses) emit an empty fragment rather than a
        wrong concrete type."""

        @dataclass
        class _Free:
            extra: Any = None

        props = dataclass_to_json_schema(_Free)["properties"]
        assert props["extra"] == {"default": None}

    async def test_unresolvable_forward_ref_falls_back_to_permissive_string(self) -> None:
        """Annotations that cannot be resolved (stale forward refs) must not
        crash spec generation: the parameter degrades to a permissive string."""
        reg = Registry("fwd")

        async def exotic(x: "NotResolvable") -> dict:  # type: ignore[name-defined]  # noqa: F821
            return {}

        capability(reg, name="exotic", description="exotic")(exotic)
        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert schema["properties"]["x"] == {"type": "string"}
        assert schema["required"] == ["x"]

    def test_handler_without_signature_degrades_to_empty_schema(self) -> None:
        """Callables that resist signature introspection (builtins) produce an
        empty object schema instead of raising."""
        reg = Registry("builtin")
        capability(reg, name="least", description="builtin")(min)
        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert schema == {"type": "object", "properties": {}, "required": []}


class _StubServer:
    """Minimal mcp.server.Server stand-in: captures decorated handlers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.handlers: dict[str, Any] = {}

    def list_tools(self):
        def decorator(fn):
            self.handlers["list_tools"] = fn
            return fn

        return decorator

    def call_tool(self):
        def decorator(fn):
            self.handlers["call_tool"] = fn
            return fn

        return decorator


class _StubTool:
    def __init__(self, *, name: str, description: Any, inputSchema: Any) -> None:
        self.name = name
        self.description = description
        self.inputSchema = inputSchema


class _StubTextContent:
    def __init__(self, *, type: str, text: str) -> None:
        self.type = type
        self.text = text


class _StubErrorData:
    def __init__(self, *, code: int, message: str) -> None:
        self.code = code
        self.message = message


class _StubMcpError(Exception):
    def __init__(self, error: _StubErrorData) -> None:
        super().__init__(error.message)
        self.error = error


def _install_stub_sdk(monkeypatch) -> None:
    """Install the stub `mcp` package (the real one is an optional extra)."""
    import sys
    import types as types_mod

    mcp_pkg = types_mod.ModuleType("mcp")
    server = types_mod.ModuleType("mcp.server")
    server.Server = _StubServer  # type: ignore[attr-defined]
    mcp_types = types_mod.ModuleType("mcp.types")
    mcp_types.Tool = _StubTool  # type: ignore[attr-defined]
    mcp_types.TextContent = _StubTextContent  # type: ignore[attr-defined]
    mcp_types.ErrorData = _StubErrorData  # type: ignore[attr-defined]
    mcp_types.McpError = _StubMcpError  # type: ignore[attr-defined]
    mcp_pkg.server = server  # type: ignore[attr-defined]
    mcp_pkg.types = mcp_types  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp", mcp_pkg)
    monkeypatch.setitem(sys.modules, "mcp.server", server)
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types)


def _echo_registry() -> Registry:
    reg = Registry("mcpdemo")

    @capability(reg, name="echo", description="echo back")
    def echo(text: str) -> dict:
        return {"text": text}

    @capability(reg, name="blast", description="must fail")
    def blast() -> dict:
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError("mcpdemo", ErrorSuffix.UNAVAILABLE, "down")

    @capability(reg, name="ping", description="no inputs")
    def ping() -> dict:
        return {"pong": True}

    return reg


class TestBuildServer:
    def test_missing_sdk_raises_runtime_error(self, monkeypatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "mcp", None)
        from platform_capability.gen_mcp import build_server

        with pytest.raises(RuntimeError, match="MCP SDK"):
            build_server(_echo_registry())

    async def test_list_tools_publishes_registry_specs(self, monkeypatch) -> None:
        _install_stub_sdk(monkeypatch)
        from platform_capability.gen_mcp import build_server

        reg = _echo_registry()
        server = build_server(reg)
        tools = await server.handlers["list_tools"]()
        assert [t.name for t in tools] == ["blast", "echo", "ping"]  # registry order
        assert tools[1].inputSchema["properties"]["text"] == {"type": "string"}
        assert tools[1].description == "echo back"

    async def test_call_tool_executes_and_wraps_json(self, monkeypatch) -> None:
        import json

        _install_stub_sdk(monkeypatch)
        from platform_capability.gen_mcp import build_server

        server = build_server(_echo_registry())
        blocks = await server.handlers["call_tool"]("echo", {"text": "hi"})
        (block,) = blocks
        assert block.type == "text"
        assert json.loads(block.text) == {"text": "hi"}

    async def test_call_tool_accepts_missing_arguments(self, monkeypatch) -> None:
        """arguments=None degrades to an empty call: the falsy-arguments
        branch serves zero-input capabilities."""
        import json

        _install_stub_sdk(monkeypatch)
        from platform_capability.gen_mcp import build_server

        server = build_server(_echo_registry())
        blocks = await server.handlers["call_tool"]("ping", None)
        assert json.loads(blocks[0].text) == {"pong": True}

    async def test_call_tool_serializes_dataclass_and_to_dict_results(self, monkeypatch) -> None:
        """Non-dict results are normalized before JSON wrapping: dataclasses
        via asdict, objects exposing to_dict via that method."""
        import dataclasses
        import json

        @dataclasses.dataclass
        class _Out:
            ok: bool

        class _WithToDict:
            def to_dict(self) -> dict:
                return {"converted": True}

        reg = Registry("shapes")

        @capability(reg, name="shaped", description="dataclass out")
        def shaped() -> _Out:
            return _Out(ok=True)

        @capability(reg, name="converted", description="to_dict out")
        def converted() -> _WithToDict:
            return _WithToDict()

        _install_stub_sdk(monkeypatch)
        from platform_capability.gen_mcp import build_server

        server = build_server(reg)
        (shaped_block,) = await server.handlers["call_tool"]("shaped", {})
        (converted_block,) = await server.handlers["call_tool"]("converted", {})
        assert json.loads(shaped_block.text) == {"ok": True}
        assert json.loads(converted_block.text) == {"converted": True}

    async def test_call_tool_maps_service_error_to_mcp_error(self, monkeypatch) -> None:
        import json

        _install_stub_sdk(monkeypatch)
        from platform_capability.gen_mcp import build_server

        server = build_server(_echo_registry())
        with pytest.raises(_StubMcpError) as exc:
            await server.handlers["call_tool"]("blast", {})
        assert exc.value.error.code == -32000
        envelope = json.loads(exc.value.error.message)
        assert envelope["error"]["code"] == "MCPDEMO.UNAVAILABLE"
