"""Prompt asset tests: the definitions tree loads, composes, and renders.

Locks the three load-time guarantees the loader promises — every definition
composes to plain text, common-block references never leak into composed
strings, and render is strict about template/value drift — plus spot checks
on the prompts the conversational closing depends on.
"""

import pytest
from agent.prompts import _RAW, P, _compose, render


def _leaves(raw, path=()):
    for key, value in raw.items():
        if isinstance(value, dict):
            yield from _leaves(value, (*path, key))
        else:
            yield (*path, key), value


def _get(path):
    node = P
    for part in path:
        node = getattr(node, part)
    return node


def test_every_definition_composes_to_text():
    for path, _raw in _leaves(_RAW):
        assert isinstance(_get(path), str), f"non-text leaf at {path}"


def test_common_references_never_leak_into_composed_strings():
    for path, _raw in _leaves(_RAW):
        assert "@common." not in _get(path), f"unresolved reference at {path}"


def test_compose_reference_resolution_and_errors():
    common = {"greeting": "你好", "nested": ["line", "@common.greeting"]}
    assert _compose(["@common.greeting"], common, "t") == "你好"
    assert _compose(["@common.nested"], common, "t") == "line\n你好"
    with pytest.raises(ValueError, match="unknown common reference"):
        _compose(["@common.missing"], common, "t")
    with pytest.raises(ValueError, match="must be strings or arrays of strings"):
        _compose(["@common.table"], {"table": {"a": "x"}}, "t")
    with pytest.raises(ValueError, match="must be strings"):
        _compose(["ok", 3], common, "t")


def test_render_substitutes_strictly():
    assert render("你好 {name}", name="世界") == "你好 世界"
    assert render("{a}-{a}", a="x") == "x-x"
    assert render("no placeholders") == "no placeholders"
    with pytest.raises(ValueError, match="missing render value"):
        render("你好 {name}")
    with pytest.raises(ValueError, match="unused render values"):
        render("plain", name="世界")


def test_render_leaves_json_and_empty_braces_alone():
    template = '输出 JSON:{"score": 0.9} 或空对象 {};共 {n} 条'
    assert render(template, n=3) == '输出 JSON:{"score": 0.9} 或空对象 {};共 3 条'


def test_global_rules_layer():
    rules = P.common.global_rules.splitlines()
    assert len(rules) == 9
    assert rules[0].startswith("Honesty first")
    # The Chinese-reply rule survives the anglicization: replies stay Chinese
    assert "Chinese" in rules[1]


def test_conversational_closing_carries_the_chat_discipline():
    discipline = P.common.chat_reply_discipline
    assert "「最终答案」" in discipline
    assert P.modes.cot.chat_synthesis.endswith(discipline)
    assert P.modes.plan_execute.chat_report.endswith(discipline)
    # The task-mode closings keep the workflow narration the chat ones drop
    assert "final answer" in P.modes.cot.synthesis
    assert "final answer" in P.modes.plan_execute.report


def test_templates_render_to_wire_text():
    assert "at most 12 steps" in render(P.modes.cot.plan, max_steps=12)
    assert '{"ranking": ["letter of the best option", ...]}' in render(P.modes.tot.judge, n=3)
    assert render(P.modes.step_instruction, index=1, total=3, step="查资料").startswith(
        "[Step 1/3] 查资料"
    )
    assert render(
        P.context.status_line.line,
        window_tokens=100,
        max_output_tokens=8,
        used_pct=5,
        auto_compact_at_pct=75,
    ).startswith("[Context status] window 100 tok")
    assert P.master.chat_goal.startswith("与用户对话")
