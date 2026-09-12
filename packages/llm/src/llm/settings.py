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
        description="Default model (empty = provider's default_model)",
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
]
