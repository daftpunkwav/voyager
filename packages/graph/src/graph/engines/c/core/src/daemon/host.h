/*
 * host.h — Lifecycle owner for the mandatory per-account engine daemon.
 */
#ifndef ENGINE_DAEMON_HOST_H
#define ENGINE_DAEMON_HOST_H

#include "daemon/ipc.h"
#include "daemon/service.h"

#include <stdatomic.h>

typedef struct {
    const engine_daemon_ipc_endpoint_t *endpoint;
    engine_daemon_build_identity_t identity;
    const char *executable_path;
    atomic_int *stop_requested;
    /* Born via `daemon start`: the generation survives its last client
     * disconnect and the no-client initial window; it stops only through the
     * stop/drain ops or an explicit process kill. */
    bool permanent;
} engine_daemon_host_config_t;

/* Blocks for the complete daemon generation. The first admitted frontend owns
 * startup; the final disconnect triggers terminal shutdown of operations,
 * watcher, UI, and runtime in that order. */
int engine_daemon_host_run(const engine_daemon_host_config_t *config);

#endif /* ENGINE_DAEMON_HOST_H */
