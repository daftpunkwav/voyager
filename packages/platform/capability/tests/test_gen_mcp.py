"""Tests for MCP generation: JSON Schema derivation and tool specs (pure
functions).
"""

from dataclasses import dataclass

from platform_capability import Registry, build_tool_specs, capability, dataclass_to_json_schema


@dataclass
class _In:
    text: str
    count: int = 3
    ratio: float = 0.5
    flag: bool = False
    tags: list | None = None
    meta: dict | None = None


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

    async def test_varargs_skipped_and_unannotated_params_stay_any(self) -> None:
        reg = Registry("misc")

        @capability(reg, name="flex", description="flexible")
        def flex(a, *args, extra: dict | None = None, **kwargs) -> dict:
            return {}

        schema = build_tool_specs(reg)[0]["inputSchema"]
        assert set(schema["properties"]) == {"a", "extra"}
        assert schema["properties"]["a"] == {}
        assert schema["properties"]["extra"] == {"type": "object"}

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
