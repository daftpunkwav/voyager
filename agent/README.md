# agent

## Purpose

The agent (Harness layer): event loop, master orchestration, subagents, context/memory, policy, tools, skills, plugins.

## Configuration

agent.* settings keys (see settings.py groups: rounds/context/fs/network/llm/memory/skills/outreach/execution).

## Extension Points

New tool = one file under tools/<group>/; new capability = one file under capabilities/<group>/ (same name, same engine — parity); new mode = one file under subagent/modes/.

## Model Experience

This IS the model experience: tool descriptions, confirm dialogs, memory, context budgets.

## Known Limitations

Single-process, single-user by design.

## Deferred Work

Multi-agent supervisor beyond the current tree (phase 20 scope).
