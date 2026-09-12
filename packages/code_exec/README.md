# code_exec

## Purpose

Code execution domain: run snippets/files in runtimes (python/node/shell), docker-first with explicit host fallback.

## Configuration

code_exec.* settings: runtimes table, timeout, memory, network mode, host-fallback switch.

## Extension Points

New runtime = an entry in code_exec.runtimes.

## Model Experience

Tools (when enabled): code_exec__run_snippet / run_file (async JobRef; results via task.* events) and list_runtimes. Complements the agent's synchronous run_shell.

## Known Limitations

Default-off (docker is environment-dependent); artifacts under workspace/sandbox.

## Deferred Work

Per-runtime resource quotas; output streaming.
