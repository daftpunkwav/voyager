# agent

## Purpose

The agent: event loop, master orchestration, subagents, context/memory, policy, tools, skills, plugins.

## Configuration

`agent.*` settings keys (declared in settings.py; among others the groups rounds / context / fs / network / llm / memory / skills / outreach / execution).

## Extension Points

New tool = one file under tools/<group>/; new capability = one file under capabilities/<group>/ (same name, same engine — parity); new mode = one file under subagent/modes/.

## Model Experience

What the model interacts with lives here: tool descriptions, confirm dialogs, memory, context budgets.

## Known Limitations

Single-process, single-user by design.

## Deferred Work

Multi-agent supervision beyond the current in-process instance tree.
