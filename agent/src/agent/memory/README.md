# memory

## Purpose

Four memory kinds (profile/episodic/semantic/working) plus retrieval, distillation, and the episodic recorder.

## Configuration

agent.memory.* keys (retention, distill interval, context cards).

## Extension Points

New store = one sibling module wired through Memory; the recorder and distiller are the only writers besides tools.

## Model Experience

Model-agnostic; agents see memory via recall_memory/get_memory tools.

## Known Limitations

Vector channel needs an embedder (llm.embedding_model); lexical otherwise.

## Deferred Work

Cross-session semantic consolidation.
