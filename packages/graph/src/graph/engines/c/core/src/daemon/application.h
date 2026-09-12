/*
 * application.h — Daemon-owned engine application sessions and thin-client wire.
 *
 * The runtime authenticates a local process and owns connection lifetime. This
 * layer owns everything above that boundary: one isolated MCP session per
 * connection, explicit workspace context, shared watcher subscriptions,
 * daemon-owned index jobs, and one update-check generation. Frontends never
 * construct stores or watchers.
 */
#ifndef ENGINE_DAEMON_APPLICATION_H
#define ENGINE_DAEMON_APPLICATION_H

#include "daemon/runtime.h"
#include "daemon/project_lock.h"
#include "mcp/index_supervisor.h"
#include "mcp/mcp.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct engine_config;
struct engine_watcher;

typedef struct engine_daemon_application engine_daemon_application_t;
typedef void *engine_daemon_application_worker_t;
typedef void *engine_daemon_application_update_worker_t;

/* Injectable physical-worker boundary. Production uses index_supervisor;
 * tests use this to deterministically hold/release one shared job. */
typedef struct {
    void *context;
    int (*start)(void *context, const char *args_json, size_t memory_budget_bytes,
                 const char *marker_file, const char *quarantine_file,
                 engine_daemon_application_worker_t *worker_out);
    engine_index_worker_poll_t (*poll)(void *context, engine_daemon_application_worker_t worker,
                                    const engine_index_worker_result_t **result_out);
    bool (*cancel)(void *context, engine_daemon_application_worker_t worker);
    const char *(*log_path)(void *context, engine_daemon_application_worker_t worker);
    void (*destroy)(void *context, engine_daemon_application_worker_t worker);
} engine_daemon_application_worker_ops_t;

typedef enum {
    ENGINE_DAEMON_APPLICATION_UPDATE_POLL_ERROR = -1,
    ENGINE_DAEMON_APPLICATION_UPDATE_POLL_RUNNING = 0,
    ENGINE_DAEMON_APPLICATION_UPDATE_POLL_TERMINAL = 1,
} engine_daemon_application_update_poll_t;

/* Injectable update-check boundary. Production supervises one curl process;
 * tests provide an offline worker. latest_version_out is borrowed from the
 * worker and is only meaningful for a clean terminal result. RUNNING is the
 * only non-terminal poll result; ERROR is a contained terminal failure. cancel
 * must be safe concurrently with poll, and destroy receives only a terminal
 * worker. */
typedef struct {
    void *context;
    int (*start)(void *context, engine_daemon_application_update_worker_t *worker_out);
    engine_daemon_application_update_poll_t (*poll)(void *context,
                                                 engine_daemon_application_update_worker_t worker,
                                                 const char **latest_version_out);
    bool (*cancel)(void *context, engine_daemon_application_update_worker_t worker);
    void (*destroy)(void *context, engine_daemon_application_update_worker_t worker);
} engine_daemon_application_update_ops_t;

typedef struct {
    struct engine_watcher *watcher;                           /* borrowed; daemon lifetime */
    struct engine_config *config;                             /* borrowed; daemon lifetime */
    const engine_daemon_application_worker_ops_t *worker_ops; /* NULL = production */
    const engine_daemon_application_update_ops_t *update_ops; /* NULL = production */
    /* Maximum distinct, non-terminal physical index jobs. Zero selects the
     * conservative daemon default (4). Identical requests still coalesce even
     * while the limit is full. */
    size_t physical_job_limit;
    /* Aggregate budget shared by every concurrently admitted physical worker.
     * The daemon host supplies its already-resolved engine process budget. */
    size_t aggregate_memory_budget_bytes;
    /* Borrowed native-lock manager for daemon-owned mutations (MCP tools,
     * watcher/UI operations). Index workers create and own their independent
     * process-local manager; the daemon job registry reserves index projects
     * in-process and must not hold the worker's OS lease. */
    engine_project_lock_manager_t *project_locks;
    /* Copied at construction. A production host supplies one fresh 32-byte
     * secret per daemon generation; tests may omit it when readiness is not
     * under test. */
    const uint8_t *ui_readiness_secret;
    size_t ui_readiness_secret_length;
} engine_daemon_application_config_t;

typedef enum {
    ENGINE_DAEMON_APPLICATION_REQUEST_SET_CONTEXT = 1,
    ENGINE_DAEMON_APPLICATION_REQUEST_MCP = 2,
    ENGINE_DAEMON_APPLICATION_REQUEST_TOOL = 3,
    ENGINE_DAEMON_APPLICATION_REQUEST_HOOK_AUGMENT = 4,
    ENGINE_DAEMON_APPLICATION_REQUEST_SET_UI_CONFIG = 5,
    ENGINE_DAEMON_APPLICATION_REQUEST_UI_READINESS_PROOF = 6,
} engine_daemon_application_request_kind_t;

typedef enum {
    ENGINE_DAEMON_APPLICATION_UI_CONFIG_ENABLED = 1U << 0,
    ENGINE_DAEMON_APPLICATION_UI_CONFIG_PORT = 1U << 1,
} engine_daemon_application_ui_config_mask_t;

engine_daemon_application_t *engine_daemon_application_new(const engine_daemon_application_config_t *config);

/* A PERMANENT application layer (backing a `daemon start` generation) keeps
 * admitting new sessions after its last live session ends; only the explicit
 * stop/drain paths latch it stopping. */
void engine_daemon_application_set_permanent(engine_daemon_application_t *application, bool permanent);

/* Cancel and reap all daemon-owned operations within timeout_ms. Normal final
 * client shutdown calls this before watcher/store teardown. Idempotent. */
bool engine_daemon_application_shutdown(engine_daemon_application_t *application, uint32_t timeout_ms);
/* Destroy application storage only after every borrowed callback and physical
 * operation is quiescent. Returns false without freeing anything when the
 * timeout expires; the caller must retain both the application and every
 * borrowed dependency, then retry or fail-stop the owning process. */
bool engine_daemon_application_free_with_timeout(engine_daemon_application_t *application,
                                              uint32_t timeout_ms);
bool engine_daemon_application_free(engine_daemon_application_t *application);

/* Callbacks are borrowed from application and remain valid until free. */
engine_daemon_runtime_application_callbacks_t engine_daemon_application_runtime_callbacks(
    engine_daemon_application_t *application);

/* Thin-client request helpers. Every helper performs one bounded runtime
 * exchange. MCP notifications succeed with a NULL/zero response. Returned
 * response bytes are malloc-owned and include one trailing NUL for text use;
 * response_length excludes that terminator. */
engine_daemon_runtime_application_status_t engine_daemon_application_client_set_context(
    engine_daemon_runtime_client_t *client, const char *session_root, const char *allowed_root,
    engine_mcp_tool_profile_t tool_profile, const char *hook_event, const char *hook_dialect,
    uint32_t timeout_ms);

/* Persist a masked UI configuration mutation in the daemon. A zero/unknown
 * mask, an invalid port, or a non-canonical unused field is rejected before
 * transport. */
engine_daemon_runtime_application_status_t engine_daemon_application_client_set_ui_config(
    engine_daemon_runtime_client_t *client, uint8_t update_mask, bool ui_enabled, int ui_port,
    uint32_t timeout_ms);

/* Ask the authenticated daemon generation to prove possession of its private
 * readiness secret for this caller-supplied challenge. The secret itself never
 * crosses IPC. Both challenge and proof are exactly one SHA-256 digest. */
engine_daemon_runtime_application_status_t engine_daemon_application_client_ui_readiness_proof(
    engine_daemon_runtime_client_t *client, const uint8_t challenge[32], uint8_t proof_out[32],
    uint32_t timeout_ms);

engine_daemon_runtime_application_status_t engine_daemon_application_client_mcp(
    engine_daemon_runtime_client_t *client, const char *message, uint8_t **response_out,
    uint32_t *response_length_out, uint32_t timeout_ms);

/* Cancellable frontend variant using a token reserved on the runtime client. */
engine_daemon_runtime_application_status_t engine_daemon_application_client_mcp_tagged(
    engine_daemon_runtime_client_t *client, engine_daemon_runtime_application_token_t request_token,
    const char *message, uint8_t **response_out, uint32_t *response_length_out,
    uint32_t timeout_ms);

engine_daemon_runtime_application_status_t engine_daemon_application_client_tool(
    engine_daemon_runtime_client_t *client, const char *tool_name, const char *args_json,
    uint8_t **response_out, uint32_t *response_length_out, uint32_t timeout_ms);

engine_daemon_runtime_application_status_t engine_daemon_application_client_hook_augment(
    engine_daemon_runtime_client_t *client, const char *input_json, uint8_t **response_out,
    uint32_t *response_length_out, uint32_t timeout_ms);

/* Watcher callback: atomically validates project/root ownership and subscribes
 * the shared physical job to every exact live session watch. The callback is
 * only a result waiter, so disconnecting the final matching owner cancels the
 * job even while unrelated daemon sessions remain. Returns 0 on success,
 * positive when stale, cancelled, or busy (retry), and negative on a terminal
 * worker error. */
int engine_daemon_application_watcher_index(const char *project_name, const char *root_path,
                                         void *context);

/* Shared daemon/UI entry point for a default full index operation. */
int engine_daemon_application_index(engine_daemon_application_t *application, const char *project_name,
                                 const char *root_path);

/* Non-blocking mutation lease for daemon-owned UI endpoints. A successful
 * begin must be paired with end. Returns false while the project (or global
 * project set "*") is reserved by indexing, another mutation, or shutdown. */
bool engine_daemon_application_project_mutation_try_begin(engine_daemon_application_t *application,
                                                       const char *project);
void engine_daemon_application_project_mutation_end(engine_daemon_application_t *application,
                                                 const char *project);

/* Read-only coordination metrics used by daemon diagnostics/tests. */
size_t engine_daemon_application_active_jobs(engine_daemon_application_t *application);
size_t engine_daemon_application_job_subscribers(engine_daemon_application_t *application,
                                              const char *project_key);
size_t engine_daemon_application_physical_job_limit(engine_daemon_application_t *application);
size_t engine_daemon_application_worker_memory_budget_bytes(engine_daemon_application_t *application);

#endif /* ENGINE_DAEMON_APPLICATION_H */
