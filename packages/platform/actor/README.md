# platform/actor — Actors and authentication

- Actor model: `{ kind: user | agent | external, id, scopes[] }` (contract in platform_contracts);
- Local authentication: a machine-local secret is generated on first startup and signs/verifies HMAC session tokens;
- **No backdoor for the agent**: the agent holds its own actor credentials and passes the same checks as the user;
- Credential passing: `ActorContext` flows along the call chain; `restrict()` can only narrow it, and no step may elevate privileges.

---

## Purpose

Actor model (user/agent/external/system + id + scopes) and local machine-token authentication; ActorContext flows through call chains and can only be narrowed.

## Configuration

None (token file path injected).

## Extension Points

New actor kind = a contract change in platform_contracts plus checks here.

## Known Limitations

HMAC token only (no refresh/rotation UI).

## Deferred Work

Token revocation list.
