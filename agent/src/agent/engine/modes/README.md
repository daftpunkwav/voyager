# modes — execution strategies for subagent runs

One file per mode. Importing the package imports every mode module, and each registers its runner in `registry.py` at import time; `base.run_mode()` dispatches through the registry, so `base.py` never imports the mode modules and the dependency graph stays one-way. The consumer is `engine/instance.py`: `run_turn()` executes one mode via `run_mode` with that turn's toolbelt view.

## Files

- base.py — `Mode` enum (react / plan_execute / cot / tot / got / reflexion / direct), `ModeLimits` (independent round and tool-call caps), callback contracts, shared step helpers, and the `run_mode` dispatcher
- registry.py — the mode-to-runner map; `runner_for()` raises a readable error on an unknown mode
- react.py — the reasoning-acting loop; the only agent-loop implementation (the context governor and editor integrate here)
- plan_execute.py — plan, then stepwise execution with a bounded replan when a step fails, then a final answer with per-step status
- cot.py — decompose the task into numbered steps, execute each as a bounded slice, synthesize the answer
- tot.py — generate candidate approaches, judge and rank them, expand the top K into drafts, pick the winner, hand it to the ReAct loop when a toolbelt exists
- got.py — answer from M fixed angles in parallel, aggregate into one draft, refine the draft against the angle outputs, and hand it to the ReAct loop when a toolbelt exists
- reflexion.py — attempt, self-review (ADEQUATE or REVISE with lessons), retry with the lessons appended to the transcript; an unreadable review accepts the draft
- direct.py — a single completion round; streams when the LLM supports it
- streaming.py — per-round streaming plumbing: delta coalescing, first-token timing, stream-or-complete tiering, cancelled-anchor history entries

## Mode selection

- `orchestrator/dispatch.py` resolves the mode per dispatch: the spawn argument, else the custom subagent's own mode; the orchestrator persona is forced to react; an unknown value fails with the list of valid modes.
- Checkpoint resume accepts react only (`engine/spawn.py`).
- Persona definitions carry a `default_mode` value (`personas/definitions/*.toml`), surfaced by the `list_personas` capability.
