# Bilingual documentation

English | [中文](README.zh.md)

Every document under `docs/` is maintained in English and Simplified Chinese as equal-authority pairs. This page defines the pair shape and the consistency record. The writing rules live in [../AGENTS.md](../AGENTS.md).

## Pair shape

A pair is three sibling files in the same directory:

- `foo.md` — the English document.
- `foo.zh.md` — the Chinese counterpart, linking back right after its H1 (`[English](foo.md) | 中文`); the English side reciprocates (`English | [中文](foo.zh.md)`).
- `foo.i18n.yaml` — the consistency record: the git blob hash of each side as of the last confirmed-consistent state.

```yaml
foo.md: 3f786850e387550fdab836ed7e6dc881de23001b
foo.zh.md: 89e6c98d92887913cadf06b2adb97f26cde4849b
```

## Structure mirroring

Heading depths and order, list kinds, ordered-list starts, table row and column counts, and verbatim code blocks match one to one across the pair. Relative links between bilingual documents use the target side's locale; links to source files keep the real path.

## Updating a pair

When a change edits either side:

1. Update the counterpart in the same change, patching minimally against the edited side's diff — not by re-translating whole files.
2. Re-record both hashes:

```sh
git hash-object docs/subsystems/foo.md docs/subsystems/foo.zh.md
# put both hashes into docs/subsystems/foo.i18n.yaml
```

A recorded hash pair whose sides no longer match means the pair is out of sync and needs the same two-step repair.

## Terminology

Keep technical terms stable across the corpus: capability → 能力, domain → 域, tool → 工具, setting → 设置(键), event → 事件, subagent → 子代理, turn/round → turn/轮, workspace → 工作区, persona → 人格, skill → 技能, memory → 记忆, checkpoint → 检查点, trajectory → 轨迹. When a term is clearer in English (e.g. `write_roots`, `parity`, `wiring`), keep the English term in both languages.
