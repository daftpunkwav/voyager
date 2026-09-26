# Agent memory, skills, personas

English | [中文](agent-memory.zh.md)

Source: `agent/src/agent/memory/`, `skills/`, `personas/`.

## Memory stores

`memory/__init__.py` — `Memory(root, embedder=None)` owns four stores under `data/runtime/agent/memory/`:

- `ProfileMemory` (`profile.db`) — key/value user profile.
- `EpisodicMemory` (`episodic.db`) — per-tool-call trail; the toolbelt's episode recorder writes every executed call.
- `SemanticMemory` (`semantic.db`) — subject/relation/object facts.
- `WorkingMemory` — in-memory recent user/assistant turns.

`recall(query, limit=8)` aggregates lexical hits across profile/episodic/semantic plus an optional vector channel (`memory/vector.py` with the injected embedder; unavailable embeddings degrade to an `EmbeddingUnavailable` note). `purge(retention_days)` honors `agent.memory.retention_days` (0 = agent-managed); `clear(zone)` wipes a zone.

## Distillation

`distill.py` — `Distiller.maybe_distill()` fires every `agent.memory.distill_interval` turns: one LLM call producing strict JSON that lands in profile/semantic writes. A re-extracted fact with the same subject+relation but a new object supersedes the older distilled fact (`SemanticMemory.add(supersede=True)`); facts from other writers are never touched. Distillation reads working memory, never the full log.

## Read policy

`read_policy.py` — `render_relevant_recall` is the relevance layer of the per-turn context row: recalled facts render content-addressed (same facts → same bytes) so the row stays byte-stable across turns when the input has not changed.

## Chat sessions

`sessions/store.py` — `SessionStore` (`data/runtime/agent/sessions.db`): `SessionMeta`/`SessionSnapshot`, the active-session pointer, and legacy single-row migration. `SessionManager` (`sessions/manager.py`) layers identity, lifecycle, per-session locks, and the raw-round recorder hookup on top.

## Skills

`skills/loader.py` — `SkillLoader(roots)` scans roots for `<name>/SKILL.md`, cached per root on the sorted `(path, mtime)` set so unchanged trees are not re-read. `index()` returns name + first-line description (≤120 chars) only; `full_text(name)` loads on demand (unreadable → `KeyError`). `add_root`/`remove_root` support plugin hot-load/unload. Built-in roots: `agent/src/agent/skills/builtin` and `workspace/skills`.

`skills/organizer.py` — `SkillOrganizer` inspects episodic memory for repeated consecutive tool-call sequences (≥2 distinct tools) and emits non-blocking `skill.proposed` events on the `agent.skills.organize_every` cadence; saving goes through the `skill` tool's propose action.

## Personas

`personas/base.py` — `Persona(key, display_name, style, system_prompt, default_mode="react", tool_allow=None)` (frozen). `personas/__init__.py` loads every `personas/definitions/*.toml` at import; duplicate keys fail loudly. Built-in responsibility keys: `orchestrator`, `recon`, `explainer`, `organizer`, `graph_guide` (legacy aliases fold via `ALIASES`; `resolve_persona` returns None for unknown or user-defined names).
