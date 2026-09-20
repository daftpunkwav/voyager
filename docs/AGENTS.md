# AGENTS.md — Documentation standard

This file defines the structure of `docs/`, the bilingual pairing contract, and the writing rules for every document here. For document placement questions, start from the [index](README.md).

## Document structure

Documents live in category directories:

| Path | Category | Contains |
|---|---|---|
| `docs/` root | Overview | The [index](README.md), [architecture](architecture.md), [development](development.md), [testing](testing.md) |
| `subsystems/` | Subsystem references | One page per backend subsystem or domain: what it is, its types, endpoints, storage, and events. Index in [subsystems/README.md](subsystems/README.md) |
| `catalog/` | Catalog references | Generated-surface style inventories: the agent tool surface ([tool-catalog](catalog/tool-catalog.md)), registered settings keys ([config-catalog](catalog/config-catalog.md)), runtime data layout ([data-layout](catalog/data-layout.md)) |
| `web/` | Frontend references | The browser application: [frontend](web/frontend.md) |
| `i18n/` | Translation process | The [pairing contract](i18n/README.md) |

A document's subject and tree position fix its scope: describe the owning subsystem's types, semantics, endpoints, and storage; describe sibling subsystems only by their interaction surface, and link to the owning page for detail. Testing mechanisms belong in [testing.md](testing.md); higher documents link there.

## Bilingual pairing

Every document in this tree is maintained as a three-file pair:

- `foo.md` — the English source.
- `foo.zh.md` — the Chinese counterpart.
- `foo.i18n.yaml` — the consistency record holding the git blob hash of each side as of the last confirmed-consistent state.

Both languages carry equal authority; the pair must say the same thing. Rules:

- The Chinese file links back immediately after its H1: `[English](foo.md) | 中文`. The English file reciprocates: `English | [中文](foo.zh.md)`.
- Structure mirrors the counterpart: heading depths and order, list kinds, table row and column counts, and verbatim code blocks match one to one. Relative links between bilingual documents use the target side's locale (`foo.zh.md` links to `bar.zh.md`); links to source files keep the real path.
- After editing either side, update the counterpart in the same change, then re-record both hashes with `git hash-object <file>` (see the [pairing contract](i18n/README.md)).

## Writing rules

- **Document current state, not change history.** Name live mechanisms, not commits, PRs, or "previously/now". State the current fact.
- **Face the code.** Every non-obvious claim is backed by a path, type name, endpoint, or setting key. Reference code as `path/to/file.py` relative to the repository root, or `module.py` relative to the document's subsystem when the context is unambiguous.
- **Neutral and verifiable.** Describe what the code does, including limits and failure behavior. Do not state unverified behavior; if a fact could not be confirmed in source, omit it rather than guess.
- **One physical line per paragraph.** Use editor soft-wrap. Code blocks, tables, and list structure keep their formatting.
- **No catalog restatement.** Where source or a generator is authoritative (tool names, settings keys, endpoints), catalog documents summarize and link to the declaring module; do not hand-copy exhaustively in multiple homes. Each fact has one home; elsewhere, link there.
- **Write directly.** Name actors, files, and facts. Avoid metaphorical load-bearing terms; say the exact type, API, or operation.
- **No implementation-status annotations.** "Planned", "TODO", and "future" notes do not belong in these documents; the repo layout and issue tracker carry status.

## Slop checklist

Hunt these in any document:

- The same rule stated in more than one home. Grep a distinctive phrase; keep one home and link the rest.
- Narrated history: "previously", "now", "no longer", "renamed". State the current fact.
- Hand-restated inventories of tests, packages, or keys when source is authoritative.
- Reasoning transcripts: implementation narration, proof of obvious branches, rejected alternatives. Keep the resulting contract; delete the derivation path.
- Emphasis inflation: bold or CAPS everywhere means nothing stands out.
- Paragraph walls: one paragraph carrying several rules and asides. Split it.
