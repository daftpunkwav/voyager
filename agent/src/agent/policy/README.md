# policy

## Purpose

Permission engine: network/fs/app/shell decisions plus approval memory.

## Configuration

agent.network.* / agent.fs.* / agent.app.* keys (hot-read).

## Extension Points

One dimension = one file (decide_* function); engine only dispatches.

## Model Experience

Model-agnostic; surfaces as L1 notify / L2 confirm dialogs.

## Known Limitations

Approval matching is exact (tool, target); no path patterns.

## Deferred Work

Scoped wildcards for approvals.
