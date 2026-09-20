# Security Policy

## Supported versions

Only the `main` branch receives security fixes. There are no tagged releases.

## Reporting a vulnerability

Report privately by email to **daftpunk.wav@outlook.com**. Please do not open
public issues for security reports.

Include a description of the issue, reproduction steps or a proof of concept,
the affected paths, and your assessment of severity. You will receive an
acknowledgment within 7 days and status updates while a fix is in progress.

## Deployment model

Voyager is a local-first, single-user application: the default assembly binds
the gateway to loopback, and there is no multi-tenant deployment. Security
review should weigh that model — a finding that requires network-reachable
access is still valid (the gateway does accept non-loopback bindings), but the
local-only default is part of the threat model, not an oversight.

## Scope notes

Security-relevant surfaces, in rough priority order:

- **Secrets at rest** — `packages/platform/secrets/src/platform_secrets/`
  (`key_material.py`, `store.py`): Fernet key derivation from
  `SECRETS_ENCRYPTION_KEY` / `SECRET_KEY`, secret storage and redaction.
  Documented sample values are rejected at load time; short key material
  logs a startup warning.
- **Gateway auth and exposure** — `packages/gateway/src/gateway/rest.py`
  (token check: without a presented token, only loopback counts as the local
  user and non-loopback gets a 401; this holds once a token is configured,
  which the default assembly always does — with no configured token every
  origin is treated as local) and
  `packages/gateway/src/gateway/ratelimit.py` (request rate limiting), plus
  the upload path in `packages/gateway/src/gateway/uploads.py`.
- **SSRF guard** — `packages/platform/webguard/src/platform_webguard/`
  (`url_policy.py`, `dns_pin.py`, `redirects.py`, `body.py`): URL validation,
  DNS pinning, and redirect handling applied to outbound URL capture.
- **Agent tool permissions** — `agent/src/agent/policy/` (`permissions.py`,
  `decision.py`, `shell.py`): the `agent.permissions` mode/allow/deny policy
  for tool calls, and the write confirmation gate for user-configured write
  roots.
- **Workspace containment** — `agent/src/agent/tools/workspace/` (`jail.py`,
  `workdir.py`): path containment for the agent's file and shell tools.

Findings outside the surfaces above are equally welcome. Secret hygiene note:
`.env` files are blocked from committing by a pre-commit hook; if real key
material ever lands in the tree, rotate it regardless of removal.
