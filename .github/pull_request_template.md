<!--
The PR title becomes the permanent commit message on main (squash merge).
Keep it Conventional Commits: `<type>(<scope>): <lowercase subject>`, 72
chars max. One PR does one thing; merge requirements live in the branch
ruleset (2 approvals, threads resolved, up to date with main).
-->

## What

<!-- What changed. One paragraph or a short list; lead with the behavior. -->

## Why

<!-- The problem or motivation. Link the issue if one exists ("Fixes #123"). -->

## How

<!-- What a reviewer should know: key decisions, alternatives considered
and rejected, boundaries touched (domains, import graph, web app). Delete
this section if the diff is self-explanatory. -->

## Verification

<!-- Which checks ran and how it was confirmed. CI runs the same gates;
local runs catch failures before the push. List anything skipped. -->
- [ ] Tests added or updated — a bug fix ships a regression test that fails
      before the fix and passes after it
- [ ] `uv sync` (environment in place)
- [ ] `npm run lint:py` · `npm run typecheck:py` · `npm run test:py`
- [ ] `npm run graph:check` (import boundaries)
- [ ] `npm run lint:web` · `npm run typecheck:web` · `npm run test:web:cov`
- [ ] `npm run i18n:web` · `npm run format:web` · `npm run build:web`
- [ ] Docs changes: `npm run docs:i18n` · `npm run docs:links`
- [ ] e2e-relevant changes: `npm run test:e2e -w web` (playwright chromium)
- [ ] Anything the tests cannot reach was verified manually (describe below)

<!-- Manual steps, before/after output. Delete if empty. -->

## Compatibility impact

<!-- Breaking changes, affected parties, migration path. Write "none" if
not — state it explicitly. -->

## Security and supply chain

<!-- Does the change touch authentication or trust boundaries, uv.lock /
package manifests, or GitHub workflows? security.yml audits on every PR
regardless of paths — use this section to give the reviewer context the
audits cannot infer. Otherwise write "N/A". -->

## Reviewer notes

<!-- Non-obvious trade-offs, known follow-ups, areas that deserve extra
scrutiny. Delete if empty. -->
