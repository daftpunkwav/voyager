/*
 * daemon.h — Process-local coordination and wire framing for the engine daemon.
 *
 * Transport and worker supervision live outside this module. The coordinator
 * binds clients and resource subscriptions to transport connections, coalesces
 * shared work, and defines the daemon's terminal shutdown transition.
 */
#ifndef ENGINE_DAEMON_H
#define ENGINE_DAEMON_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Permanent framing version for the account-wide rendezvous endpoint. Never
 * bump this for detailed runtime payload changes: incompatible executable
 * generations must still exchange the stable HELLO conflict envelope. */
#define ENGINE_DAEMON_RENDEZVOUS_FRAME_VERSION 1U
#define ENGINE_DAEMON_FRAME_HEADER_SIZE 12U
#define ENGINE_DAEMON_MAX_FRAME_SIZE (10U * 1024U * 1024U)
#define ENGINE_DAEMON_KEY_SIZE 17U

typedef enum {
    ENGINE_DAEMON_FRAME_REQUEST = 1,
    ENGINE_DAEMON_FRAME_RESPONSE = 2,
} engine_daemon_frame_type_t;

typedef struct {
    engine_daemon_frame_type_t type;
    uint16_t flags;
    uint32_t length;
} engine_daemon_frame_t;

typedef struct engine_daemon_coordinator engine_daemon_coordinator_t;

typedef uint64_t engine_daemon_client_id_t;
typedef uint64_t engine_daemon_subscription_id_t;

#define ENGINE_DAEMON_CLIENT_ID_INVALID ((engine_daemon_client_id_t)0)
#define ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID ((engine_daemon_subscription_id_t)0)

typedef enum {
    ENGINE_DAEMON_COORDINATOR_RUNNING = 1,
    ENGINE_DAEMON_COORDINATOR_STOPPING = 2,
} engine_daemon_coordinator_state_t;

typedef enum {
    ENGINE_DAEMON_SUBSCRIPTION_REJECTED = 0,
    ENGINE_DAEMON_SUBSCRIPTION_STARTED = 1,
    ENGINE_DAEMON_SUBSCRIPTION_JOINED = 2,
} engine_daemon_subscription_result_t;

typedef enum {
    ENGINE_DAEMON_JOB_NONE = 0,
    ENGINE_DAEMON_JOB_RUNNING = 1,
    ENGINE_DAEMON_JOB_CANCEL_REQUESTED = 2,
    ENGINE_DAEMON_JOB_REAPING = 3,
} engine_daemon_job_state_t;

typedef void (*engine_daemon_job_cancel_fn)(const char *project_key, void *context);
typedef void (*engine_daemon_watch_release_fn)(const char *project_key, void *context);

typedef struct {
    engine_daemon_job_cancel_fn cancel_job;
    engine_daemon_watch_release_fn release_watch;
    void *context;
} engine_daemon_coordinator_hooks_t;

/* lease_timeout_ms is fixed for the coordinator lifetime. All timestamps must
 * come from the same monotonic clock domain. */
engine_daemon_coordinator_t *engine_daemon_coordinator_new(uint64_t lease_timeout_ms);

/* A PERMANENT coordinator (backing a `daemon start` generation) never
 * self-transitions to STOPPING when its client count reaches zero; only the
 * explicit stop/drain paths end it. */
void engine_daemon_coordinator_set_permanent(engine_daemon_coordinator_t *coordinator, bool permanent);
/* The caller must first quiesce coordinator calls and hook invocations. */
void engine_daemon_coordinator_free(engine_daemon_coordinator_t *coordinator);

/* Hooks are copied. Their context must remain valid until the coordinator is
 * quiescent. Hooks are always invoked after releasing the coordinator mutex. */
bool engine_daemon_coordinator_set_hooks(engine_daemon_coordinator_t *coordinator,
                                      const engine_daemon_coordinator_hooks_t *hooks);
engine_daemon_coordinator_state_t engine_daemon_coordinator_state(engine_daemon_coordinator_t *coordinator);

/* Client IDs are daemon-issued, nonzero, monotonic, and never recycled. */
engine_daemon_client_id_t engine_daemon_client_connected(engine_daemon_coordinator_t *coordinator,
                                                   uint64_t now_ms);
bool engine_daemon_client_disconnected(engine_daemon_coordinator_t *coordinator,
                                    engine_daemon_client_id_t client_id, uint64_t now_ms);
bool engine_daemon_client_heartbeat(engine_daemon_coordinator_t *coordinator,
                                 engine_daemon_client_id_t client_id, uint64_t now_ms);
size_t engine_daemon_expire_leases(engine_daemon_coordinator_t *coordinator, uint64_t now_ms);
size_t engine_daemon_active_clients(engine_daemon_coordinator_t *coordinator);

/* Every accepted subscription receives a unique daemon-issued handle. The
 * first subscriber starts the physical resource; later subscribers join it. */
engine_daemon_subscription_result_t engine_daemon_job_subscribe(
    engine_daemon_coordinator_t *coordinator, engine_daemon_client_id_t client_id,
    const char *project_key, engine_daemon_subscription_id_t *subscription_id);
engine_daemon_subscription_result_t engine_daemon_watch_subscribe(
    engine_daemon_coordinator_t *coordinator, engine_daemon_client_id_t client_id,
    const char *project_key, engine_daemon_subscription_id_t *subscription_id);
bool engine_daemon_job_unsubscribe(engine_daemon_coordinator_t *coordinator,
                                engine_daemon_client_id_t client_id,
                                engine_daemon_subscription_id_t subscription_id);
bool engine_daemon_watch_unsubscribe(engine_daemon_coordinator_t *coordinator,
                                  engine_daemon_client_id_t client_id,
                                  engine_daemon_subscription_id_t subscription_id);

size_t engine_daemon_job_subscribers(engine_daemon_coordinator_t *coordinator, const char *project_key);
size_t engine_daemon_watch_subscribers(engine_daemon_coordinator_t *coordinator, const char *project_key);
size_t engine_daemon_active_jobs(engine_daemon_coordinator_t *coordinator);
size_t engine_daemon_active_watches(engine_daemon_coordinator_t *coordinator);
engine_daemon_job_state_t engine_daemon_job_state(engine_daemon_coordinator_t *coordinator,
                                            const char *project_key);

/* Cancellation is two phase. Losing the final subscriber requests cancel;
 * the job remains active until its supervisor reports completion/reaping. */
bool engine_daemon_job_reaping(engine_daemon_coordinator_t *coordinator, const char *project_key);
bool engine_daemon_job_reaped(engine_daemon_coordinator_t *coordinator, const char *project_key,
                           uint64_t now_ms);
bool engine_daemon_job_completed(engine_daemon_coordinator_t *coordinator, const char *project_key,
                              uint64_t now_ms);

/* STOPPING is terminal. Exit is ready only after every job/watch is gone. */
bool engine_daemon_should_exit(engine_daemon_coordinator_t *coordinator, uint64_t now_ms);

/* Encode/decode the permanently stable 12-byte "EngineD" rendezvous frame header
 * in network byte order. Detailed operation ABIs live above this framing. */
bool engine_daemon_frame_header_encode(uint8_t header[ENGINE_DAEMON_FRAME_HEADER_SIZE],
                                    engine_daemon_frame_type_t type, uint16_t flags, uint32_t length);
bool engine_daemon_frame_header_decode(const uint8_t header[ENGINE_DAEMON_FRAME_HEADER_SIZE],
                                    engine_daemon_frame_t *frame);

#endif /* ENGINE_DAEMON_H */
