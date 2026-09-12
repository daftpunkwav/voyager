"""ask_user tool: the model picks the answer form and fills the options;
count limits are enforced per kind.

- choice / multi_choice: 2-8 options, plus a permanent free-text input on the
  dialog (the user can always answer with their own words);
- slider: 1-8 tick labels rendered as a labeled discrete scale;
- rating: fixed 5-star review, answered as an integer 1-5;
- text / confirm: no options needed.

Anything unknown degrades gracefully on the frontend (rendered as free text).
"""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.interact.question_broker import AskUser, Question

#: Keys tried (in order) when an option arrives as an object instead of a string;
#: the LLM occasionally wraps choice labels like {"content": "..."}.
_OPTION_KEYS = ("content", "label", "value", "text")

#: Answer forms the model may pick from; anything unknown degrades gracefully
#: on the frontend (rendered as a plain free-text dialog).
_KINDS = ("confirm", "choice", "multi_choice", "slider", "rating", "text")

#: Per-kind option-count bounds (lo, hi); kinds absent from the map take no
#: options (confirm / rating / text reject a non-empty list).
_KIND_OPTION_LIMITS: dict[str, tuple[int, int]] = {
    "choice": (2, 8),
    "multi_choice": (2, 8),
    "slider": (1, 8),
}


def _coerce_option(opt: Any) -> str:
    """Normalize one choice option to display text: strings pass through,
    objects collapse to their first known label key, anything else to str()."""
    if isinstance(opt, str):
        return opt
    if isinstance(opt, dict):
        for key in _OPTION_KEYS:
            value = opt.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return " ".join(f"{k}: {v}" for k, v in opt.items() if v) or str(opt)
    return str(opt)


def _validate_options(kind: str, safe_options: list[str]) -> str | None:
    """Enforce the per-kind option-count bounds; returns a model-actionable
    error text when the count is off (the question is not published then —
    a broken dialog must never flash in front of the user)."""
    if kind in ("confirm", "rating", "text"):
        if safe_options:
            return f"[参数错误] ask_user(kind={kind}) 不接受 options,请去掉该参数"
        return None
    bounds = _KIND_OPTION_LIMITS.get(kind)
    if bounds is None:
        return None
    lo, hi = bounds
    if not lo <= len(safe_options) <= hi:
        return (
            f"[参数错误] ask_user(kind={kind}) 选项个数须在 {lo}-{hi} 之间,"
            f"当前 {len(safe_options)} 个;另有常驻自由输入,无需为覆盖所有情况堆选项"
        )
    return None


def ask_user_tool(asker: AskUser) -> AgentTool:
    async def ask_user(
        prompt: str,
        kind: str = "confirm",
        options: list[str] | None = None,
        min: float | None = None,  # mirrors the Question model field
        max: float | None = None,
    ) -> Any:
        # The payload goes straight to the UI as React children: options must be
        # strings whatever the LLM sent, deduplicated in order (a duplicate label
        # would collide as a React key and double-count against the bounds)
        safe_options = list(
            dict.fromkeys(_coerce_option(o) for o in (options or []) if _coerce_option(o))
        )
        invalid = _validate_options(kind, safe_options)
        if invalid is not None:
            return invalid
        answer = await asker.ask(
            Question(prompt=prompt, kind=kind, options=tuple(safe_options), min=min, max=max)
        )
        return answer if answer is not None else "(用户超时未答)"

    return AgentTool(
        name="ask_user",
        description=(
            "向用户提问,回答形态由你自由决定:"
            "confirm 确认(是/否) / choice 单选(2-8 个选项) / multi_choice 多选(2-8 个选项,"
            "返回数组) / slider 滑块(1-8 个刻度标签) / rating 五星评价(返回 1-5) / text 纯填空。"
            "每个对话框都带一个常驻自由输入,用户随时可能绕过选项直接打字——"
            "把返回值原样当作用户的真实意图处理即可。"
        ),
        handler=ask_user,
        schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "kind": {"type": "string", "enum": list(_KINDS)},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "选项列表:choice/multi_choice 需 2-8 个;slider 需 1-8 个刻度标签;"
                        "confirm/rating/text 不需要"
                    ),
                },
                "min": {"type": "number", "description": "slider 数值下限(配刻度标签可省略)"},
                "max": {"type": "number", "description": "slider 数值上限(配刻度标签可省略)"},
            },
            "required": ["prompt"],
        },
    )


__all__ = ["ask_user_tool"]
