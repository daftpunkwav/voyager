"""LLM service settings: default provider/model and sampling
parameters — not secrets; users and agents have equal access.
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="llm.default_provider",
        module="llm",
        type=SettingType.STR,
        default="",
        description="Default provider id (see list_providers)",
    ),
    SettingDef(
        key="llm.default_model",
        module="llm",
        type=SettingType.STR,
        default="",
        description=(
            "Model chosen in the chat composer picker; empty = the provider's first enabled model"
        ),
    ),
    SettingDef(
        key="llm.pricing",
        module="llm",
        type=SettingType.JSON,
        default={},
        description=(
            "Price table for read-side cost conversion, USD per 1M tokens: "
            '{"<model or prefix>": {"input": 2.5, "output": 10.0}}; '
            '"*" is the catch-all for totals. Unpriced models report no cost.'
        ),
    ),
    SettingDef(
        key="llm.embedding_model",
        module="llm",
        type=SettingType.STR,
        default="",
        description="Embedding model for the embed capability and memory vector recall (empty = lexical recall only)",
    ),
    SettingDef(
        key="llm.reasoning_effort",
        module="llm",
        type=SettingType.STR,
        default="",
        description=(
            "Reasoning-effort override resolved against the serving model's "
            "configured thinking variants (empty = follow the model's "
            "thinking_default; off = explicitly disabled; otherwise a variant "
            "name). chat/responses pass it verbatim; anthropic maps the "
            "canonical low/medium/high to thinking budgets and derives other "
            "variants' budgets from their position in the variants list."
        ),
    ),
    SettingDef(
        key="llm.temperature",
        module="llm",
        type=SettingType.FLOAT,
        default=0.7,
        min=0.0,
        max=2.0,
        description="Sampling temperature (global default)",
    ),
    SettingDef(
        key="llm.max_output_tokens",
        module="llm",
        type=SettingType.INT,
        default=4096,
        min=64,
        max=128000,
        description="Max output tokens (global default)",
    ),
    SettingDef(
        key="llm.request_timeout_s",
        module="llm",
        type=SettingType.INT,
        default=60,
        min=10,
        max=600,
        description=(
            "LLM request timeout (seconds). Streaming: cap on the gap between "
            "SSE chunks; non-streaming derives a larger whole-generation cap "
            "from max_tokens. Raise for slow providers or long thinking."
        ),
    ),
    SettingDef(
        key="llm.retry_attempts",
        module="llm",
        type=SettingType.INT,
        default=2,
        min=0,
        max=6,
        description="Retries for transient LLM errors (5xx / 429 / connect blips)",
    ),
    SettingDef(
        key="llm.retry_backoff_s",
        module="llm",
        type=SettingType.FLOAT,
        default=0.5,
        min=0.05,
        max=30.0,
        description="Base exponential backoff between LLM retries (seconds)",
    ),
]
