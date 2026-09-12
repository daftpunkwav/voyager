/* project_lock.h — Shared daemon/local-CLI project mutation leases. */
#ifndef ENGINE_DAEMON_PROJECT_LOCK_H
#define ENGINE_DAEMON_PROJECT_LOCK_H

#include "daemon/ipc.h"
#include "foundation/lock_registry.h"

#include <stdint.h>

typedef struct engine_project_lock_manager engine_project_lock_manager_t;
typedef struct engine_project_lock_lease engine_project_lock_lease_t;

/* Each manager is an independent process-local registry over the endpoint's
 * owner-only runtime directory. Separate engine processes therefore coordinate
 * through the same native lock files without sharing memory. */
engine_project_lock_manager_t *engine_project_lock_manager_new(const engine_daemon_ipc_endpoint_t *endpoint);

/* Normal projects hold SH(project-set) + EX(project). "*" holds
 * EX(project-set), blocking every named project. Project lock keys are ASCII
 * case-folded to cover filename aliases on case-insensitive filesystems. */
engine_private_file_lock_status_t engine_project_lock_acquire(engine_project_lock_manager_t *manager,
                                                        const char *project, uint64_t deadline_ms,
                                                        const engine_lock_cancel_token_t *cancel_token,
                                                        engine_project_lock_lease_t **lease_out);

/* One fair, nonblocking attempt for UI/watcher paths. */
engine_private_file_lock_status_t engine_project_lock_try_acquire(engine_project_lock_manager_t *manager,
                                                            const char *project,
                                                            engine_project_lock_lease_t **lease_out);

engine_private_file_lock_status_t engine_project_lock_lease_release(engine_project_lock_lease_t **lease_io);

engine_private_file_lock_status_t engine_project_lock_request_cancel(engine_project_lock_manager_t *manager,
                                                               engine_lock_cancel_token_t *token);

/* Refuses teardown while any lease/cleanup state remains. */
engine_private_file_lock_status_t engine_project_lock_manager_free(
    engine_project_lock_manager_t **manager_io);

#endif /* ENGINE_DAEMON_PROJECT_LOCK_H */
