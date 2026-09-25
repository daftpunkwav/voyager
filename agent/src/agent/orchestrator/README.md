# orchestrator

## Purpose

Orchestration: message arbitration, dispatch, task graph joins, blackboard, proactive outreach, turn evaluation.

## Configuration

agent.outreach.* / agent.triggers.* keys.

## Extension Points

New orchestration concern = one sibling module (task_graph/blackboard/proactive pattern).

## Model Experience

Model-agnostic; agents experience it via spawn/board/reach_out surfaces.

## Known Limitations

Tree-shaped dependencies only (no DAG engine).

## Deferred Work

Cross-session task coordination.
