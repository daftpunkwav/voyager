# prompts — central LLM prompt assets

Every LLM prompt in the agent package lives in `definitions/*.toml`, never in
business code. Modules read composed text as `P.modes.cot.synthesis` and fill
runtime values with `render(P.modes.cot.plan, max_steps=12)`; the loader
(`prompts/__init__.py`) parses the TOML at import time and fails loudly on
duplicate domains, dangling references, or non-text values — the same
authoring discipline as `agent/personas`.

## Layout

One file per domain, one top-level table per file (the domain name):

- `common.toml` — base-layer blocks any domain may compose from (`@common.<key>`)
- `modes.toml` — subagent execution modes (react / cot / tot / got / plan_execute / reflexion)
- `context.toml` — compaction planning, plan review gate, context status line
- `memory.toml` — long-term distillation
- `orchestrator.toml` — arbitration, synthesis, proactive outreach, chat goal, task-completion evaluation, notice bodies
- `runtime.toml` — loop advisory, structured-output instruction

Personas (`agent/personas/definitions/*.toml`) and builtin skills
(`agent/skills/builtin/*/SKILL.md`) are separate prompt assets with their own
loaders and stay where they are.

## Authoring rules

- Composition: a value may be an array of lines; elements join with newlines.
  An element starting with `@common.` pulls in that common block. References
  point into `common` only (domain → base, one-way, loader-enforced).
- Placeholders: `{name}` tokens are substituted at the call site by
  `render()`; a missing or unused keyword is an error. JSON braces in a prompt
  (`{"score": ...}`) never match the placeholder pattern.
- Multi-line text: use TOML multi-line basic strings (`"""`); the opening
  newline is trimmed, everything else (including trailing newlines that are
  part of the prompt) is byte-exact. `*.toml` is pinned to LF in
  `.gitattributes` so prompt bytes stay stable across platforms.
- Structured lists (a menu, a ruleset) are arrays too; consumers recover the
  items with `splitlines()` — no item may itself contain a newline.

Editing a prompt never requires touching a `.py` file; adding a prompt means
adding a key here and reading it where it is used.
