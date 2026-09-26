# Agent context engineering

English | [中文](agent-context.zh.md)

How the model-visible prompt is assembled, budgeted, pruned, compacted, and monitored for cache health.

Source: `agent/src/agent/context/`

## Prompt assembly

`builder.py` — `ContextBuilder.system(...)` composes the system prompt in a fixed, byte-stable order (prefix-cache friendly):

1. `【全局规则】` — `prompts/definitions/common.toml` (`common.global_rules`)
2. Scoped rules — `workspace/AGENTS.md`
3. `【用户准则】` — setting `agent.conduct`
4. Persona system prompt
5. `【人格准则】` — `agent.guidelines[persona]`
6. `【风格】` — `agent.style` / per-persona `agent.style.overrides`
7. `【可用 skill】` — name + one-line index only (texts load on demand)

The head ends with the stable tail: user profile, task book (goal/constraints/done_when), and MCP instructions.

The per-turn volatile layers — recent memory cards, the relevance-recall section (`read_policy.py`), in-flight subagent digests, the user's current page context, and plan review-phase state (`plan_gate.py`) — do not live in the system prompt: `ContextBuilder.turn_context()` renders them into ONE trailing user-role row (marked `【会话状态】`) appended after the full history. Providers cache the byte-prefix of the whole request, so keeping the system prompt byte-stable across turns is what makes the history prefix cacheable; the usage status line rides the same row.

Each turn, `engine/turn.py:run_turn` rebuilds the system prompt (byte-stable unless a source changed) and re-renders the context row; on a mid-turn resume the snapshot's row is refreshed in place. History is bounded by `ContextBudget`.

## Budgets

`budgets.py` — `ContextBudget` dataclass; `budget_from_settings(settings, model_name)` resolves per-model window profiles (`agent.context.model_profiles`) and the usable window. Notable defaults: `HISTORY_MAX=60` cross-turn entries (dropped in pairs), `COMPRESS_BUDGET=6000`, `auto_compact_at=75` (% usable window), `compact_target` = 40% when unset, memory/recall/skill/digest/profile/task/page character caps. All are settings-backed under `agent.context.*` ([config-catalog.md](../catalog/config-catalog.md)).

`runtime/tokenizer.py` — CJK-aware token estimation (lives in the runtime layer, shared by context and runtime).

## Governor

`governor.py` — `ContextGovernor.enforce()` is the per-turn authority:

1. `prune()` (`prune.py`) — deterministic rolling microcompact: old oversized tool results shrink to `…[已压缩]` markers, protected by `agent.context.prune_protect_tokens` (default 4000) and bounded by `prune_min_tokens`.
2. `compact()` (`editor.py` `compact_transcript`) — if still over threshold: an LLM-planned transcript restructure (plan path primary, deterministic fallback), with `CompactionBackoff` (`MAX_REMAINING_RATIO = 0.8`) suppressing repeated low-yield plans. The summary re-enters history as a user message tagged `[历史压缩]`.

`compressor.py` — `compress(messages, budget)`: deterministic truncation of old tool results, then pair-shaped eviction of oldest entries (an assistant+tool run is never split), always keeping the most recent 8.

## Cache monitoring

`prefix_watch.py` — `PrefixWatch`: turn-level hashes of the system prompt and tool roster, round-level cache health from provider-reported `cached_tokens` (warm-then-cold = break; miss threshold 1000 tokens), and per-message hash diff for localization. Findings log to `agent.context.prefix`.

## On-demand loading and page context

`loader.py` — `OnDemandLoader` supplies `skill_text` and `recall` payloads only when the builder asks. `pages.py` — `PageContextRegistry` holds the frontend-reported current page (capability `report_page_context`); the builder renders it into the per-turn context row under a character cap (`agent.context.page_chars`).
