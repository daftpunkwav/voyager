"""Guard: prompt text stays in the prompts module, not in business code.

The modules below had their LLM prompt literals migrated to
agent/prompts/definitions/*.toml; this scan keeps them from growing new
module-level prompt constants (any uppercase ``PROMPT`` token) — new or
changed prompts belong in the TOML data files, read through
``agent.prompts.P``.
"""

from pathlib import Path

# Business modules whose prompt literals moved to prompts/definitions/.
GUARDED_MODULES = [
    "engine/modes/cot.py",
    "engine/modes/plan_execute.py",
    "engine/modes/tot.py",
    "engine/modes/got.py",
    "engine/modes/react.py",
    "engine/modes/reflexion.py",
    "context/editor.py",
    "context/plan_gate.py",
    "context/usage.py",
    "memory/distill.py",
    "orchestrator/arbiter.py",
    "orchestrator/synthesize.py",
    "orchestrator/proactive.py",
    "orchestrator/goal_driver.py",
    "orchestrator/sessions.py",
    "orchestrator/master.py",
    "runtime/evaluation.py",
    "runtime/loop_advisory.py",
    "llm_structured.py",
    "build.py",
]


def test_business_modules_hold_no_prompt_constants():
    src = Path(__file__).parents[2] / "src" / "agent"
    offenders = [
        rel for rel in GUARDED_MODULES if "PROMPT" in (src / rel).read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"prompt constants back in business code (move them to "
        f"prompts/definitions/*.toml): {offenders}"
    )
