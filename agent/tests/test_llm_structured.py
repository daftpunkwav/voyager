"""Tests for the structured output engine: JSON extraction, schema normalization,
Pydantic model validation, and resilient completion with error-feedback retries.
"""

from __future__ import annotations

import pytest
from agent.llm import FakeLLM, LLMReply
from agent.llm_structured import (
    SchemaSpec,
    StructuredResult,
    complete_structured,
    extract_json_from_text,
    to_schema_spec,
    validate_structured_data,
)
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    name: str = Field(description="User's full name")
    age: int = Field(description="User's age in years")
    is_active: bool = True
    interests: list[str] = Field(default_factory=list)


DICT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "score": {"type": "integer"},
    },
    "required": ["summary", "score"],
}


class TestJsonExtraction:
    def test_direct_json(self) -> None:
        raw = '{"name": "Alice", "age": 30}'
        assert extract_json_from_text(raw) == {"name": "Alice", "age": 30}

    def test_markdown_code_fence(self) -> None:
        text = 'Here is the result:\n```json\n{"name": "Bob", "age": 25}\n```\nHope this helps!'
        assert extract_json_from_text(text) == {"name": "Bob", "age": 25}

    def test_markdown_fence_without_json_tag(self) -> None:
        text = '```\n{"score": 100, "summary": "great"}\n```'
        assert extract_json_from_text(text) == {"score": 100, "summary": "great"}

    def test_embedded_braces(self) -> None:
        text = 'Prefix text {"status": "ok", "code": 200} suffix text'
        assert extract_json_from_text(text) == {"status": "ok", "code": 200}

    def test_invalid_text_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="could not extract valid JSON"):
            extract_json_from_text("Sorry, I am unable to generate JSON.")


class TestSchemaNormalization:
    def test_dict_normalization(self) -> None:
        spec = to_schema_spec(DICT_SCHEMA, name="review_schema")
        assert spec.name == "review_schema"
        assert spec.schema == DICT_SCHEMA
        assert spec.strict is True

    def test_pydantic_normalization(self) -> None:
        spec = to_schema_spec(UserProfile)
        assert spec.name == "UserProfile"
        assert "properties" in spec.schema
        assert "name" in spec.schema["properties"]
        assert "age" in spec.schema["properties"]

    def test_schema_spec_passthrough(self) -> None:
        orig = SchemaSpec(name="custom", schema={"type": "object"})
        assert to_schema_spec(orig) is orig


class TestValidation:
    def test_dict_schema_valid(self) -> None:
        data = {"summary": "done", "score": 95}
        valid, val, err = validate_structured_data(data, DICT_SCHEMA)
        assert valid is True
        assert val == data
        assert err is None

    def test_dict_schema_missing_required(self) -> None:
        data = {"summary": "done"}
        valid, _val, err = validate_structured_data(data, DICT_SCHEMA)
        assert valid is False
        assert "missing required field: 'score'" in str(err)

    def test_dict_schema_wrong_type(self) -> None:
        data = {"summary": "done", "score": "ninety-five"}
        valid, _val, err = validate_structured_data(data, DICT_SCHEMA)
        assert valid is False
        assert "expected integer" in str(err)

    def test_pydantic_validation_success(self) -> None:
        data = {"name": "Charlie", "age": 28, "interests": ["coding", "music"]}
        valid, val, err = validate_structured_data(data, UserProfile)
        assert valid is True
        assert isinstance(val, UserProfile)
        assert val.name == "Charlie"
        assert val.age == 28
        assert val.interests == ["coding", "music"]
        assert err is None

    def test_pydantic_validation_failure(self) -> None:
        data = {"name": "David", "age": "not-a-number"}
        valid, _val, err = validate_structured_data(data, UserProfile)
        assert valid is False
        assert err is not None


class TestCompleteStructured:
    async def test_success_direct_dict(self) -> None:
        fake_llm = FakeLLM([LLMReply(text='{"summary": "passed", "score": 100}')])
        res: StructuredResult[dict] = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "analyze this test"}],
            schema=DICT_SCHEMA,
        )
        assert res.ok is True
        assert res.value == {"summary": "passed", "score": 100}
        assert res.retries_used == 0
        # Verify response_format was passed in call
        assert fake_llm.calls[0].get("response_format") is not None

    async def test_success_pydantic_model(self) -> None:
        fake_llm = FakeLLM(
            [LLMReply(text='```json\n{"name": "Alice", "age": 30, "interests": ["ai"]}\n```')]
        )
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "extract profile"}],
            schema=UserProfile,
        )
        assert res.ok is True
        assert isinstance(res.value, UserProfile)
        assert res.value.name == "Alice"
        assert res.value.age == 30
        assert res.value.interests == ["ai"]

    async def test_retry_on_malformed_json(self) -> None:
        # First round returns garbled text, second round returns valid JSON
        fake_llm = FakeLLM(
            [
                LLMReply(text="Sure! Here is the JSON: {name: 'Alice', invalid}"),
                LLMReply(text='{"name": "Alice", "age": 30}'),
            ]
        )
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "get user"}],
            schema=UserProfile,
            max_retries=2,
        )
        assert res.ok is True
        assert isinstance(res.value, UserProfile)
        assert res.value.name == "Alice"
        assert res.retries_used == 1
        assert len(fake_llm.calls) == 2
        # Check that error feedback was injected in 2nd call
        second_call_msgs = fake_llm.calls[1]["messages"]
        assert any(
            "Your previous response was not valid JSON" in str(m.get("content"))
            for m in second_call_msgs
        )

    async def test_retry_on_schema_violation(self) -> None:
        # First round returns missing required 'age' field, second round corrects it
        fake_llm = FakeLLM(
            [
                LLMReply(text='{"name": "Alice"}'),
                LLMReply(text='{"name": "Alice", "age": 22}'),
            ]
        )
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "get user"}],
            schema=UserProfile,
            max_retries=2,
        )
        assert res.ok is True
        assert res.value is not None
        assert res.value.age == 22
        assert res.retries_used == 1

    async def test_retries_exhausted(self) -> None:
        fake_llm = FakeLLM(
            [
                LLMReply(text="Bad 1"),
                LLMReply(text="Bad 2"),
            ]
        )
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "get user"}],
            schema=UserProfile,
            max_retries=1,
        )
        assert res.ok is False
        assert res.value is None
        assert res.retries_used == 1
        assert "JSON parse error" in str(res.error)

    async def test_degraded_llm_reply(self) -> None:
        fake_llm = FakeLLM([LLMReply(text="[quota exceeded]", degraded=True)])
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "get user"}],
            schema=UserProfile,
        )
        assert res.ok is False
        assert "degraded" in str(res.error)

    async def test_structured_field_already_present(self) -> None:
        # Test when the client adapter has already populated reply.structured
        fake_llm = FakeLLM(
            [
                LLMReply(
                    text='{"name": "Bob", "age": 40}',
                    structured={"name": "Bob", "age": 40},
                )
            ]
        )
        res = await complete_structured(
            fake_llm,
            [{"role": "user", "content": "get user"}],
            schema=UserProfile,
        )
        assert res.ok is True
        assert res.value is not None and res.value.name is not None
        assert res.value.name == "Bob"
        assert res.value.age == 40

    async def test_metered_llm_with_complete_structured(self) -> None:
        from agent.llm import Usage
        from agent.runtime import Meter, metered_llm

        meter = Meter()
        fake = FakeLLM(
            [
                LLMReply(
                    text='{"name": "Eve", "age": 35}',
                    usage=Usage(input_tokens=15, output_tokens=10),
                )
            ]
        )
        metered = metered_llm(fake, meter, model="gpt-4o")

        res = await complete_structured(
            metered,
            [{"role": "user", "content": "extract profile"}],
            schema=UserProfile,
        )
        assert res.ok is True
        assert res.value is not None
        assert res.value.name == "Eve"
        assert res.value.age == 35
        # Verify meter recorded the tokens
        assert meter.tokens_used_today() == 25
