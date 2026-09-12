/*
 * config.h — persisted HTTP service configuration (ui_enabled / ui_port).
 *
 * Writes config.json under the cache directory (cache root overridable via
 * ENGINE_CACHE_DIR).
 * Thread safety: load/save are independent filesystem operations.
 */
#ifndef ENGINE_UI_CONFIG_H
#define ENGINE_UI_CONFIG_H

#include <stdbool.h>

/* Default values */
/* Default sidecar port (the API side connects via GRAPH_ENGINE_URL) */
#define ENGINE_UI_DEFAULT_PORT 9750
#define ENGINE_UI_DEFAULT_ENABLED false

typedef struct {
    bool ui_enabled;
    int ui_port;
} engine_ui_config_t;

/* Load config from disk. Missing/corrupt file → defaults. */
void engine_ui_config_load(engine_ui_config_t *cfg);

/* Atomically save one complete config generation. Creates the directory if
 * needed and reports write/sync/replace failures. */
bool engine_ui_config_save(const engine_ui_config_t *cfg);

/* Get the config file path. Writes to buf (up to bufsz bytes).
 * Exposed for testing. */
void engine_ui_config_path(char *buf, int bufsz);

#endif /* ENGINE_UI_CONFIG_H */
