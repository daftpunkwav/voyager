# runtime

## Purpose

Runtime mechanisms: event loop, scheduler + durable queue, checkpoints, trajectory projection, meter/quota, trace spans, deadlines, loop guards.

## Configuration

agent.execution.* / agent.rounds.* / queue-related keys.

## Extension Points

One mechanism per file; add a sibling module, never grow an existing one across concerns.

## Model Experience

Model-agnostic machinery.

## Known Limitations

In-process only.

## Deferred Work

Distributed queue backends.
