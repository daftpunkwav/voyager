/*
 * agent_clients.h — Table-driven agent client MCP installation profiles.
 */
#ifndef ENGINE_CLI_AGENT_CLIENTS_H
#define ENGINE_CLI_AGENT_CLIENTS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ENGINE_AGENT_CLIENT_QODER = 0,
    ENGINE_AGENT_CLIENT_KIMI,
    ENGINE_AGENT_CLIENT_GITLAB_DUO,
    ENGINE_AGENT_CLIENT_ROVO_DEV,
    ENGINE_AGENT_CLIENT_AMP,
    ENGINE_AGENT_CLIENT_DEVIN,
    ENGINE_AGENT_CLIENT_TABNINE,
    ENGINE_AGENT_CLIENT_CONTINUE,
    ENGINE_AGENT_CLIENT_VISUAL_STUDIO,
    ENGINE_AGENT_CLIENT_TRAE,
    ENGINE_AGENT_CLIENT_ROO_CODE,
    ENGINE_AGENT_CLIENT_AMAZON_Q,
    ENGINE_AGENT_CLIENT_CODEBUDDY,
    ENGINE_AGENT_CLIENT_IBM_BOB_IDE,
    ENGINE_AGENT_CLIENT_IBM_BOB_SHELL,
    ENGINE_AGENT_CLIENT_POCHI,
    ENGINE_AGENT_CLIENT_PI,
    ENGINE_AGENT_CLIENT_SOURCEGRAPH_CODY,
    ENGINE_AGENT_CLIENT_COUNT
} engine_agent_client_id_t;

typedef enum {
    ENGINE_AGENT_STABLE = 0,
    ENGINE_AGENT_CONDITIONAL,
    ENGINE_AGENT_OPT_IN
} engine_agent_client_stability_t;

enum {
    ENGINE_AGENT_CAP_MCP = UINT32_C(1) << 0,
    ENGINE_AGENT_CAP_INSTRUCTIONS = UINT32_C(1) << 1,
    ENGINE_AGENT_CAP_SKILL = UINT32_C(1) << 2,
    ENGINE_AGENT_CAP_AGENT = UINT32_C(1) << 3,
    ENGINE_AGENT_CAP_HOOK = UINT32_C(1) << 4,
    ENGINE_AGENT_CAP_PLUGIN = UINT32_C(1) << 5
};

typedef int (*engine_agent_mcp_edit_fn)(engine_agent_client_id_t id, const char *config_path,
                                     const char *binary_path);

typedef struct {
    engine_agent_client_id_t id;
    const char *stable_id;
    const char *display_name;
    engine_agent_client_stability_t stability;
    uint32_t capabilities;
    const char *detection_command;
    engine_agent_mcp_edit_fn install_mcp;
    engine_agent_mcp_edit_fn remove_mcp;
} engine_agent_client_profile_t;

typedef bool (*engine_agent_probe_fn)(const char *value, const void *context);

typedef struct {
    const char *home_dir;
    const char *xdg_config_home;
    const char *appdata_dir;
    const char *glab_config_dir;
    const char *kimi_code_home;
    const char *continue_config_path;
    const char *trae_config_path;
    const char *roo_config_path;
    const char *cody_config_path;
    bool is_windows;
    engine_agent_probe_fn path_exists;
    engine_agent_probe_fn command_exists;
    const void *probe_context;
} engine_agent_client_resolve_options_t;

enum {
    ENGINE_AGENT_EDIT_ERROR = -1,
    ENGINE_AGENT_EDIT_OK = 0,
    ENGINE_AGENT_EDIT_FOREIGN = 1,
    ENGINE_AGENT_EDIT_NOT_APPLICABLE = 2
};

size_t engine_agent_client_count(void);
const engine_agent_client_profile_t *engine_agent_client_at(size_t index);
const engine_agent_client_profile_t *engine_agent_client_by_id(engine_agent_client_id_t id);
const engine_agent_client_profile_t *engine_agent_client_by_stable_id(const char *stable_id);

/* Resolves the documented user config path. Returns 0 on success, 1 when a
 * conditional target has no safe active path, and -1 for invalid input or an
 * ambiguous/unsupported configuration. */
int engine_agent_client_resolve_path(engine_agent_client_id_t id,
                                  const engine_agent_client_resolve_options_t *options, char *path_out,
                                  size_t path_out_size);
bool engine_agent_client_detect(engine_agent_client_id_t id,
                             const engine_agent_client_resolve_options_t *options);
bool engine_agent_client_cleanup_candidate(engine_agent_client_id_t id,
                                        const engine_agent_client_resolve_options_t *options);

/* config_path must already have been resolved. The adapter never guesses a
 * target here. Existing same-name foreign entries fail closed with
 * ENGINE_AGENT_EDIT_FOREIGN. Removal requires the original installed binary path
 * and only removes the still-canonical entry. */
int engine_agent_client_install_mcp(engine_agent_client_id_t id, const char *config_path,
                                 const char *binary_path);
int engine_agent_client_remove_mcp(engine_agent_client_id_t id, const char *config_path,
                                const char *binary_path);

#ifdef __cplusplus
}
#endif

#endif /* ENGINE_CLI_AGENT_CLIENTS_H */
