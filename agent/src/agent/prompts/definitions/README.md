# definitions — prompt data files (TOML)

One TOML per domain; pure data, no code. `agent/prompts/__init__.py` loads
this directory with `tomllib` at import time, composes arrays and
`@common.*` block references, and exposes the frozen tree as `P` (see
`agent/prompts/README.md` for the authoring rules). A syntax error, a
duplicate domain, or a dangling reference here is an import-time failure by
design — broken prompt data is an assembly error, not a runtime surprise.

## Files

- common.toml — base-layer blocks: the group-chat reply discipline and the
  nine global rules injected into every persona's system prompt
- modes.toml — execution-mode prompts: shared step/loop-abort scaffolds plus
  cot, plan_execute, tot, got, react, reflexion
- context.toml — transcript compaction plan, plan review gate section, and
  the cache-stable context status line
- memory.toml — long-term distillation extraction
- orchestrator.toml — chat goal, message arbitration, background-result synthesis,
  proactive greeting/follow-up, goal resume, team report / task claim notices,
  task-completion evaluation judge
- runtime.toml — loop advisory nudge, structured-output instruction
