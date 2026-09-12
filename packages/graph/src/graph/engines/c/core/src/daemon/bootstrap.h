/*
 * bootstrap.h — Process-role policy and mandatory daemon bootstrap.
 *
 * Role classification must happen before any stateful initialization in
 * main(): no store, watcher, UI, diagnostics, or index supervisor may be
 * constructed until the process is known to be the daemon, one of its
 * internal workers, a thin client, or an explicitly stateless command.
 */
#ifndef ENGINE_DAEMON_BOOTSTRAP_H
#define ENGINE_DAEMON_BOOTSTRAP_H

#include "daemon/runtime.h"
#include "daemon/version_cohort.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ENGINE_DAEMON_INTERNAL_ARG "--engine-daemon-internal"
#define ENGINE_DAEMON_PERMANENT_ARG "--engine-daemon-permanent"
#define ENGINE_DAEMON_BOOTSTRAP_LAUNCH_ARGC 3U

typedef enum {
    ENGINE_DAEMON_PROCESS_INVALID = 0,
    ENGINE_DAEMON_PROCESS_STATELESS,
    ENGINE_DAEMON_PROCESS_DAEMON,
    ENGINE_DAEMON_PROCESS_WORKER,
    ENGINE_DAEMON_PROCESS_MCP_CLIENT,
    ENGINE_DAEMON_PROCESS_LOCAL_CLI,
    ENGINE_DAEMON_PROCESS_HOOK_CLIENT,
    ENGINE_DAEMON_PROCESS_DAEMON_CTL,
} engine_daemon_process_role_t;

/* Pure argv classifier. argv[0] is the executable. The hidden daemon role is
 * accepted only as the sole argument; index workers must use the exact
 * build-bound `cli --index-worker ...` grammar. */
engine_daemon_process_role_t engine_daemon_process_role(int argc, char *const argv[]);

/* True only for externally launched long-lived frontends. Internal daemon and
 * worker processes plus one-shot local CLI calls never count as client leases. */
bool engine_daemon_process_role_requires_client(engine_daemon_process_role_t role);

/* Construct the one stable per-account endpoint. The endpoint identity is the
 * product rendezvous key: executable path, semantic version, build hash, and
 * ABI values must never create parallel daemon namespaces. */
engine_daemon_ipc_endpoint_t *engine_daemon_bootstrap_endpoint_new(const char *runtime_parent);

/* Cross-platform launch policy for the daemon child. The child is invoked
 * directly (never through a shell), with exactly argv[0] plus the one hidden
 * internal argument. It is detached from the launching client's lifetime and
 * inherits no standard handles; logical client leases govern its lifetime. */
typedef struct {
    const char *executable_path;
    const char *argv[ENGINE_DAEMON_BOOTSTRAP_LAUNCH_ARGC + 1U];
    size_t argc;
    bool detached;
    bool inherit_standard_handles;
    bool use_shell;
} engine_daemon_bootstrap_launch_spec_t;

bool engine_daemon_bootstrap_launch_spec_init(const char *executable_path,
                                           engine_daemon_bootstrap_launch_spec_t *spec_out);

/* Same launch policy, but the child is born PERMANENT: it survives its last
 * client disconnect and stops only via `daemon stop`, the install/update
 * drain, or an explicit process kill. Only `daemon start` uses this. */
bool engine_daemon_bootstrap_launch_spec_init_permanent(const char *executable_path,
                                                     engine_daemon_bootstrap_launch_spec_t *spec_out);

typedef enum {
    ENGINE_DAEMON_BOOTSTRAP_FAILED = 0,
    ENGINE_DAEMON_BOOTSTRAP_BYPASSED,
    ENGINE_DAEMON_BOOTSTRAP_CONNECTED,
    ENGINE_DAEMON_BOOTSTRAP_CONFLICT,
} engine_daemon_bootstrap_status_t;

typedef struct {
    engine_daemon_process_role_t role;
    const engine_daemon_ipc_endpoint_t *endpoint;
    const engine_daemon_build_identity_t *identity;
    const char *executable_path;
    uint32_t connect_timeout_ms;
    uint32_t startup_timeout_ms;
    /* `daemon start` only: an absent endpoint is replaced by a PERMANENT
     * generation instead of an ephemeral one. Client bootstraps leave this
     * false — they must never mint permanence implicitly. */
    bool spawn_permanent;
} engine_daemon_bootstrap_config_t;

typedef struct {
    engine_daemon_bootstrap_status_t status;
    engine_daemon_runtime_client_t *client;
    engine_daemon_runtime_connect_result_t connect_result;
    bool daemon_spawned;
    char message[ENGINE_DAEMON_CONFLICT_MESSAGE_SIZE];
} engine_daemon_bootstrap_result_t;

/* A probe distinguishes an absent endpoint from a reserved endpoint whose
 * listener is STARTING, saturated, or otherwise temporarily unable to admit
 * this client. RESERVED and TERMINAL are wait states for the observed
 * generation. If it later becomes truly absent, this same attempt re-enters
 * startup serialization and may launch exactly one replacement. */
typedef enum {
    ENGINE_DAEMON_BOOTSTRAP_PROBE_ERROR = 0,
    ENGINE_DAEMON_BOOTSTRAP_PROBE_UNAVAILABLE,
    ENGINE_DAEMON_BOOTSTRAP_PROBE_RESERVED,
    ENGINE_DAEMON_BOOTSTRAP_PROBE_CONNECTED,
    ENGINE_DAEMON_BOOTSTRAP_PROBE_CONFLICT,
    ENGINE_DAEMON_BOOTSTRAP_PROBE_TERMINAL,
} engine_daemon_bootstrap_probe_status_t;

/* Deterministic policy seam shared by production probing and unit contracts.
 * lifetime_status follows the IPC reservation tri-state (1 held, 0 free,
 * -1 error). Every protocol-level REJECTED response is RESERVED unless its
 * message explicitly reports terminal shutdown; it is never UNAVAILABLE. */
engine_daemon_bootstrap_probe_status_t engine_daemon_bootstrap_classify_failed_connect(
    const engine_daemon_runtime_connect_result_t *connect_result, int lifetime_status);

typedef void *engine_daemon_bootstrap_lock_t;
typedef void *engine_daemon_bootstrap_cohort_t;

/* Injectable OS/runtime boundary used by the deterministic unit contract.
 * Production callers use engine_daemon_bootstrap_execute(), whose built-in
 * operations delegate to daemon IPC/runtime and write visible diagnostics to
 * stderr. Lock acquisition uses the IPC tri-state convention: 1 acquired,
 * 0 held by another starter, -1 error. */
typedef struct {
    void *context;
    engine_version_cohort_status_t (*cohort_acquire)(void *context,
                                                  const engine_daemon_ipc_endpoint_t *endpoint,
                                                  const engine_daemon_build_identity_t *identity,
                                                  uint64_t deadline_ms,
                                                  engine_daemon_bootstrap_cohort_t *cohort_out,
                                                  engine_daemon_conflict_t *conflict_out);
    void (*cohort_release)(void *context, engine_daemon_bootstrap_cohort_t cohort);
    engine_daemon_bootstrap_probe_status_t (*probe)(void *context,
                                                 const engine_daemon_ipc_endpoint_t *endpoint,
                                                 const engine_daemon_build_identity_t *identity,
                                                 uint32_t timeout_ms,
                                                 engine_daemon_runtime_client_t **client_out,
                                                 engine_daemon_runtime_connect_result_t *result_out);
    int (*startup_lock_try_acquire)(void *context, const engine_daemon_ipc_endpoint_t *endpoint,
                                    engine_daemon_bootstrap_lock_t *lock_out);
    /* Called with startup serialization still held immediately before spawn.
     * It releases only migration-era compatibility ownership that the child
     * must reacquire for its lifetime; the ordinary startup lock stays held. */
    bool (*startup_lock_prepare_handoff)(void *context, engine_daemon_bootstrap_lock_t lock);
    /* Retry-safe: success consumes and clears *lock_io; false retains it. */
    bool (*startup_lock_release)(void *context, engine_daemon_bootstrap_lock_t *lock_io);
    bool (*spawn_daemon)(void *context, const engine_daemon_bootstrap_launch_spec_t *spec);
    void (*visible_diagnostic)(void *context, const char *message);
} engine_daemon_bootstrap_ops_t;

engine_daemon_bootstrap_status_t engine_daemon_bootstrap_execute(
    const engine_daemon_bootstrap_config_t *config, engine_daemon_bootstrap_result_t *result_out);

/* Test seam for the same state machine. All callbacks are synchronous and
 * borrowed for the duration of the call. */
engine_daemon_bootstrap_status_t engine_daemon_bootstrap_execute_with_ops(
    const engine_daemon_bootstrap_config_t *config, const engine_daemon_bootstrap_ops_t *ops,
    engine_daemon_bootstrap_result_t *result_out);

#endif /* ENGINE_DAEMON_BOOTSTRAP_H */
