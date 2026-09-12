"""Built-in provider catalog: pure data, extensible.

Two API formats: `chat` (OpenAI-compatible /chat/completions) and `anthropic`
(Anthropic Messages /v1/messages). Custom providers are stored through
add_provider and are not registered in this file.
"""

from __future__ import annotations

from typing import Any

BUILTIN_PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "preset_id": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_format": "chat",
        "models": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
    },
    {
        "preset_id": "anthropic",
        "display_name": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "api_format": "anthropic",
        "models": ["claude-sonnet-4-5", "claude-haiku-4-5"],
    },
    {
        "preset_id": "deepseek",
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_format": "chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "preset_id": "moonshot",
        "display_name": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "api_format": "chat",
        "models": ["kimi-k2-0905-preview", "moonshot-v1-128k"],
    },
    {
        "preset_id": "openrouter",
        "display_name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_format": "chat",
        "models": [],
    },
    {
        "preset_id": "ollama",
        "display_name": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "api_format": "chat",
        "models": [],
    },
)

_API_FORMATS = ("chat", "anthropic")


def get_preset(preset_id: str) -> dict[str, Any] | None:
    for p in BUILTIN_PROVIDERS:
        if p["preset_id"] == preset_id:
            return dict(p)
    return None


def valid_format(fmt: str) -> bool:
    return fmt in _API_FORMATS
