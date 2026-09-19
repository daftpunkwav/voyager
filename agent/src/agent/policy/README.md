# policy

## Purpose

Permission layers, two gates deep: the tool permission modes
(permissions.py — one mode + deny/allow lists from `agent.permissions`,
constraining the agent actor only) decide whether a tool call may be made
at all; the per-dimension decisions (network/fs/app/shell) then decide what
the call may touch. Approval memory (approvals.py) shortcuts the single
surviving confirmation: writes into user-configured fs write_roots.

## Configuration

agent.network.* / agent.fs.* / agent.app.* keys (hot-read), plus
agent.permissions (user_only JSON; hot-read on every call, never cached).

## Extension Points

One dimension = one file (decide_* function); engine only dispatches.
Tool permission classes live in the central TOOL_CLASS table
(permissions.py): absent entry = unknown = D (fail-closed); the surface
aggregation re-keys entries to "tool.action".

## Model Experience

Confirm dialogs exist only for write_roots writes; everything else surfaces
as L1 notify or executes directly. Permission rejections read as
`[权限拒绝] …` and state that the policy is the user's.

## Known Limitations

Approval matching is exact (tool, target); no path patterns.

## Deferred Work

Scoped wildcards for approvals.
