"""Structured output engine: schema validation, JSON repair/extraction,
and typed structured completions with automatic error-feedback retries.

Provides:
- SchemaSpec: schema definition container supporting dict and Pydantic models
- complete_structured: high-level resilient structured completion over any LLMClient
- extract_json_from_text: robust JSON extraction from markdown fences and raw text
- validate_structured_data: validation against Pydantic models or JSON schema dicts
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, is_dataclass
from typing import Any, Generic, TypeVar

from agent.llm import LLMClient, LLMReply, ToolSpec, content_to_text
from agent.prompts import P, render

log = logging.getLogger("agent.llm_structured")

T = TypeVar("T")

# Markdown code block regex for JSON extraction
_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", re.IGNORECASE)


@dataclass(frozen=True)
class SchemaSpec:
    """Target schema specification for structured generation."""

    name: str
    schema: dict[str, Any]
    description: str = ""
    strict: bool = True


@dataclass
class StructuredResult(Generic[T]):
    """Outcome of a complete_structured invocation."""

    ok: bool
    value: T | None
    raw_reply: LLMReply
    raw_json: Any = None
    error: str | None = None
    retries_used: int = 0


def extract_json_from_text(text: str) -> Any:
    """Extract and parse JSON from a model output string.

    Tolerates leading/trailing markdown code fences, explanatory prose around
    the JSON object, and whitespace.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty text cannot be parsed as JSON")

    # 1. Try parsing directly
    try:
        return json.loads(raw)
    except ValueError:
        pass

    # 2. Try markdown code block extraction
    matches = _CODE_BLOCK_RE.findall(raw)
    for match in matches:
        candidate = match.strip()
        if candidate:
            try:
                return json.loads(candidate)
            except ValueError:
                continue

    # 3. Try finding outermost balanced JSON object or array {...} / [...]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start >= 0 and end > start:
            snippet = raw[start : end + 1]
            try:
                return json.loads(snippet)
            except ValueError:
                continue

    raise ValueError(f"could not extract valid JSON from text: {raw[:120]!r}")


def to_schema_spec(target: Any, name: str | None = None) -> SchemaSpec:
    """Normalize a target schema representation to SchemaSpec.

    Supports:
    - SchemaSpec instances (returned as-is)
    - Pydantic BaseModel subclasses or instances (model_json_schema)
    - Dicts representing standard JSON Schema
    - Dataclass types
    """
    if isinstance(target, SchemaSpec):
        return target

    # Check for Pydantic BaseModel (v2 model_json_schema or v1 schema)
    if hasattr(target, "model_json_schema") and callable(target.model_json_schema):
        schema = target.model_json_schema()
        doc = getattr(target, "__doc__", "") or ""
        resolved_name: str = name or str(getattr(target, "__name__", "StructuredModel"))
        return SchemaSpec(
            name=resolved_name,
            schema=schema,
            description=doc.strip(),
            strict=True,
        )

    if hasattr(target, "schema") and callable(target.schema) and not isinstance(target, dict):
        schema = target.schema()
        resolved_name = name or str(getattr(target, "__name__", "StructuredModel"))
        return SchemaSpec(
            name=resolved_name,
            schema=schema,
            strict=True,
        )

    # Check for dict schema
    if isinstance(target, dict):
        return SchemaSpec(name=name or "structured_output", schema=target, strict=True)

    # Check for dataclass
    if is_dataclass(target):
        try:
            from pydantic import TypeAdapter

            schema = TypeAdapter(target).json_schema()
            resolved_name = name or str(getattr(target, "__name__", "DataclassModel"))
            return SchemaSpec(name=resolved_name, schema=schema)
        except Exception:  # noqa: BLE001, S110  # fallback when TypeAdapter is unavailable
            pass

    raise TypeError(f"unsupported schema target: {type(target)!r}")


def _validate_dict_schema(data: Any, schema: dict[str, Any]) -> str | None:
    """Lightweight built-in JSON schema validator when jsonschema is not installed.

    Validates top-level object type and required properties.
    Returns None if valid, or an error string if invalid.
    """
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(data, dict):
        return f"expected JSON object (dict), got {type(data).__name__}"
    if expected_type == "array" and not isinstance(data, list):
        return f"expected JSON array (list), got {type(data).__name__}"

    if isinstance(data, dict):
        required = schema.get("required") or []
        for req in required:
            if req not in data:
                return f"missing required field: {req!r}"

        properties = schema.get("properties") or {}
        type_mapping: dict[str, Any] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        for prop_name, prop_val in data.items():
            prop_spec = properties.get(prop_name)
            if prop_spec and isinstance(prop_spec, dict):
                prop_type_str = prop_spec.get("type")
                if prop_type_str in type_mapping:
                    expected_cls = type_mapping[prop_type_str]
                    # Note: bool is a subclass of int in Python, avoid false positive
                    if prop_type_str in ("integer", "number") and isinstance(prop_val, bool):
                        return f"field {prop_name!r} expected {prop_type_str}, got boolean"
                    if not isinstance(prop_val, expected_cls):
                        return f"field {prop_name!r} expected {prop_type_str}, got {type(prop_val).__name__}"

    return None


def validate_structured_data(data: Any, target: Any) -> tuple[bool, Any, str | None]:
    """Validate parsed JSON data against target schema.

    Returns:
        (is_valid, validated_value_or_original_data, error_message)
    """
    # 1. Pydantic BaseModel validation
    if hasattr(target, "model_validate") and callable(target.model_validate):
        try:
            validated = target.model_validate(data)
            return True, validated, None
        except Exception as exc:  # noqa: BLE001  # validation failure captured and returned as error
            return False, data, str(exc)

    if hasattr(target, "parse_obj") and callable(target.parse_obj):
        try:
            validated = target.parse_obj(data)
            return True, validated, None
        except Exception as exc:  # noqa: BLE001  # validation failure captured and returned as error
            return False, data, str(exc)

    # 2. SchemaSpec validation
    if isinstance(target, SchemaSpec):
        err = _validate_dict_schema(data, target.schema)
        return err is None, data, err

    # 3. Dict validation
    if isinstance(target, dict):
        err = _validate_dict_schema(data, target)
        return err is None, data, err

    return True, data, None


def build_response_format(spec: SchemaSpec, mode: str = "json_schema") -> dict[str, Any]:
    """Build the response_format dict for OpenAI-compatible wire requests."""
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": spec.name,
                "schema": spec.schema,
                "strict": spec.strict,
            },
        }
    return {"type": "json_object"}


async def complete_structured(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    schema: type[T] | dict[str, Any] | SchemaSpec,
    *,
    max_retries: int = 2,
    tools: list[ToolSpec] | None = None,
    inject_prompt: bool = True,
    name: str = "structured_output",
    response_format_mode: str = "json_schema",
) -> StructuredResult[T]:
    """Perform a structured completion with schema enforcement and error feedback retries.

    Args:
        llm: The LLMClient instance (HttpLLM, FakeLLM, metered, etc.)
        messages: Conversation messages list
        schema: Target Pydantic model class, SchemaSpec, or JSON Schema dict
        max_retries: Maximum number of correction attempts on malformed/invalid JSON
        tools: Optional tools to pass to the model
        inject_prompt: Whether to append schema instructions to the prompt
        name: Name identifier for the schema
        response_format_mode: 'json_schema' or 'json_object'
    """
    spec = to_schema_spec(schema, name=name)
    response_format = build_response_format(spec, mode=response_format_mode)

    # Prepare request messages
    req_messages = list(messages)
    if inject_prompt:
        schema_instruction = render(
            P.runtime.schema_instruction,
            schema=json.dumps(spec.schema, ensure_ascii=False, indent=2),
        )
        if req_messages and req_messages[-1].get("role") in ("user", "system"):
            last = dict(req_messages[-1])
            # Multi-modal list content is flattened to text first: str() on a
            # part list would leak Python repr into the prompt.
            last["content"] = content_to_text(last.get("content")) + schema_instruction
            req_messages[-1] = last
        else:
            req_messages.append({"role": "user", "content": schema_instruction})

    last_reply: LLMReply | None = None
    last_error: str | None = None
    parsed_json: Any = None
    use_response_format = True

    for attempt in range(max_retries + 1):
        try:
            if use_response_format:
                try:
                    reply = await llm.complete(
                        req_messages,
                        tools=tools,
                        response_format=response_format,
                    )
                except TypeError:
                    # Client does not support response_format argument
                    use_response_format = False
                    reply = await llm.complete(req_messages, tools=tools)
            else:
                reply = await llm.complete(req_messages, tools=tools)
        except Exception as exc:  # noqa: BLE001  # capture all LLM errors to return structured error
            log.warning("complete_structured LLM call failed: %s", exc)
            return StructuredResult(
                ok=False,
                value=None,
                raw_reply=LLMReply(text=str(exc), degraded=True),
                error=f"LLM call exception: {exc}",
                retries_used=attempt,
            )

        last_reply = reply
        if reply.degraded:
            return StructuredResult(
                ok=False,
                value=None,
                raw_reply=reply,
                error="LLM returned degraded response",
                retries_used=attempt,
            )

        # 1. Parse JSON from structured field or text
        parsed_json = reply.structured
        if parsed_json is None:
            text = reply.text or ""
            try:
                parsed_json = extract_json_from_text(text)
            except ValueError as val_err:
                last_error = f"JSON parse error: {val_err}"
                if attempt < max_retries:
                    log.info("retrying structured completion due to invalid JSON (%s)", val_err)
                    req_messages.append({"role": "assistant", "content": text})
                    req_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your previous response was not valid JSON ({val_err}). "
                                f"Please output valid JSON matching the schema strictly."
                            ),
                        }
                    )
                    continue
                return StructuredResult(
                    ok=False,
                    value=None,
                    raw_reply=reply,
                    error=last_error,
                    retries_used=attempt,
                )

        # 2. Validate against schema/model
        valid, val_result, val_msg = validate_structured_data(parsed_json, schema)
        if valid:
            return StructuredResult(
                ok=True,
                value=val_result,
                raw_reply=reply,
                raw_json=parsed_json,
                retries_used=attempt,
            )

        last_error = f"Schema validation failed: {val_msg}"
        if attempt < max_retries:
            log.info("retrying structured completion due to validation failure (%s)", val_msg)
            req_messages.append(
                {"role": "assistant", "content": json.dumps(parsed_json, ensure_ascii=False)}
            )
            req_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your output failed schema validation: {val_msg}. "
                        f"Please correct the JSON according to the schema requirements."
                    ),
                }
            )
            continue

        return StructuredResult(
            ok=False,
            value=None,
            raw_reply=reply,
            raw_json=parsed_json,
            error=last_error,
            retries_used=attempt,
        )

    return StructuredResult(
        ok=False,
        value=None,
        raw_reply=last_reply or LLMReply(text="retries exhausted", degraded=True),
        raw_json=parsed_json,
        error=last_error or "maximum retries exhausted",
        retries_used=max_retries,
    )


__all__ = [
    "SchemaSpec",
    "StructuredResult",
    "build_response_format",
    "complete_structured",
    "extract_json_from_text",
    "to_schema_spec",
    "validate_structured_data",
]
