/*
 * agent_profiles.h — Canonical tiered graph-engine agent profiles.
 */
#ifndef ENGINE_CLI_AGENT_PROFILES_H
#define ENGINE_CLI_AGENT_PROFILES_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ENGINE_GRAPH_TIER_SCOUT = 0,
    ENGINE_GRAPH_TIER_VERIFY,
    ENGINE_GRAPH_TIER_AUDIT,
    ENGINE_GRAPH_TIER_COUNT
} engine_graph_tier_t;

typedef enum {
    ENGINE_GRAPH_ACCESS_DIRECT = 0,
    ENGINE_GRAPH_ACCESS_HANDOFF,
    ENGINE_GRAPH_ACCESS_COUNT
} engine_graph_access_t;

typedef enum {
    ENGINE_GRAPH_DIALECT_CLAUDE = 0,
    ENGINE_GRAPH_DIALECT_CODEX,
    ENGINE_GRAPH_DIALECT_GEMINI,
    ENGINE_GRAPH_DIALECT_QWEN,
    ENGINE_GRAPH_DIALECT_COPILOT,
    ENGINE_GRAPH_DIALECT_OPENCODE,
    ENGINE_GRAPH_DIALECT_KILO,
    ENGINE_GRAPH_DIALECT_KIRO,
    ENGINE_GRAPH_DIALECT_JUNIE,
    ENGINE_GRAPH_DIALECT_QODER,
    ENGINE_GRAPH_DIALECT_CODEBUDDY,
    ENGINE_GRAPH_DIALECT_FACTORY,
    ENGINE_GRAPH_DIALECT_VIBE,
    ENGINE_GRAPH_DIALECT_AUGMENT,
    ENGINE_GRAPH_DIALECT_CURSOR,
    ENGINE_GRAPH_DIALECT_ROVO,
    ENGINE_GRAPH_DIALECT_POCHI,
    ENGINE_GRAPH_DIALECT_COUNT
} engine_graph_profile_dialect_t;

/* Stable profile identifier. VERIFY intentionally retains "graph-engine". */
const char *engine_graph_tier_slug(engine_graph_tier_t tier);
const char *engine_graph_tier_display_name(engine_graph_tier_t tier);
bool engine_graph_dialect_direct_capable(engine_graph_profile_dialect_t dialect);

/* Returns malloc-owned profile content, or NULL for invalid/unsafe combinations.
 * binary_path is required for direct Kiro and Codex profiles and ignored otherwise. */
char *engine_render_graph_profile(engine_graph_profile_dialect_t dialect, engine_graph_tier_t tier,
                               engine_graph_access_t access, const char *binary_path);

/* v0.9.1-rc.1 direct Codex rendering (server table without a transport), kept
 * so install/uninstall can recognize and migrate those files. */
char *engine_render_graph_profile_codex_rc1(engine_graph_tier_t tier);

/* Vibe stores the behavioral prompt separately from its TOML agent definition.
 * Other integrations may also use this as the canonical contract text. */
char *engine_render_graph_prompt(engine_graph_tier_t tier, engine_graph_access_t access);

#ifdef __cplusplus
}
#endif

#endif /* ENGINE_CLI_AGENT_PROFILES_H */
