/* version_cohort.h — Crash-safe exact-build admission across engine processes. */
#ifndef ENGINE_DAEMON_VERSION_COHORT_H
#define ENGINE_DAEMON_VERSION_COHORT_H

#include "daemon/ipc.h"
#include "daemon/service.h"

#include <stdint.h>

typedef struct engine_version_cohort_manager engine_version_cohort_manager_t;
typedef struct engine_version_cohort_lease engine_version_cohort_lease_t;
typedef struct engine_version_cohort_daemon_claim engine_version_cohort_daemon_claim_t;

typedef enum {
    ENGINE_VERSION_COHORT_OK = 0,
    ENGINE_VERSION_COHORT_CONFLICT = 1,
    ENGINE_VERSION_COHORT_BUSY = 2,
    ENGINE_VERSION_COHORT_UNSAFE = 3,
    ENGINE_VERSION_COHORT_IO = 4,
} engine_version_cohort_status_t;

typedef enum {
    ENGINE_VERSION_COHORT_DAEMON_ABSENT = 0,
    ENGINE_VERSION_COHORT_DAEMON_COORDINATED = 1,
    ENGINE_VERSION_COHORT_DAEMON_UNCOORDINATED = 2,
    ENGINE_VERSION_COHORT_DAEMON_UNSAFE = 3,
    ENGINE_VERSION_COHORT_DAEMON_IO = 4,
} engine_version_cohort_daemon_presence_t;

typedef enum {
    ENGINE_VERSION_COHORT_MAINTENANCE_ABSENT = 0,
    ENGINE_VERSION_COHORT_MAINTENANCE_REQUESTED = 1,
    ENGINE_VERSION_COHORT_MAINTENANCE_UNSAFE = 2,
    ENGINE_VERSION_COHORT_MAINTENANCE_IO = 3,
} engine_version_cohort_maintenance_presence_t;

/* A mutation barrier invokes its quiesce callback only after retaining the
 * admission lock and observing active lifetime participants. The callback
 * must return promptly: the barrier itself bounds only its native lock wait.
 * It returns REQUESTED, REFUSED, or ERROR; NOT_NEEDED is reserved for the API
 * output when lifetime was already free. REFUSED leaves active work untouched;
 * ERROR reports an inability to request orderly quiescence. */
typedef enum {
    ENGINE_VERSION_COHORT_QUIESCE_NOT_NEEDED = 0,
    ENGINE_VERSION_COHORT_QUIESCE_REQUESTED = 1,
    ENGINE_VERSION_COHORT_QUIESCE_REFUSED = 2,
    ENGINE_VERSION_COHORT_QUIESCE_ERROR = 3,
} engine_version_cohort_quiesce_result_t;

typedef engine_version_cohort_quiesce_result_t (*engine_version_cohort_quiesce_fn)(void *context);

/* Managers independently reopen no paths: the endpoint duplicates its
 * already-validated owner-only runtime-directory handle. All managers for one
 * account therefore meet at the same stable native lock files. */
engine_version_cohort_manager_t *engine_version_cohort_manager_new(
    const engine_daemon_ipc_endpoint_t *endpoint);

/* Admission first takes the maintenance gate SH without waiting, holds it
 * across the short admission EX transition, then retains SH on the cohort
 * lifetime file. Active maintenance therefore fails fast with BUSY. Exact
 * identity peers share SH; a different version, build, or ABI returns
 * CONFLICT with conflict_out populated. deadline_ms is an absolute
 * engine_now_ms() deadline; UINT64_MAX waits indefinitely. Every non-NULL
 * lease_out, including cleanup-only IO state, must be released. */
engine_version_cohort_status_t engine_version_cohort_acquire(engine_version_cohort_manager_t *manager,
                                                       const engine_daemon_build_identity_t *identity,
                                                       uint64_t deadline_ms,
                                                       engine_version_cohort_lease_t **lease_out,
                                                       engine_daemon_conflict_t *conflict_out);

/* Binary activation takes the lifetime file EX. It therefore refuses while
 * any CLI/bootstrap/daemon participant is active and blocks new admissions
 * for the complete install/update/uninstall mutation window. */
engine_version_cohort_status_t engine_version_cohort_reserve_exclusive(
    engine_version_cohort_manager_t *manager, uint64_t deadline_ms,
    engine_version_cohort_lease_t **lease_out);

/* Coordinated install/update/uninstall barrier for modern engine participants.
 * It first publishes maintenance intent EX, then retains admission EX so no
 * new participant can enter, and finally probes lifetime EX. If lifetime is
 * busy, quiesce is invoked exactly once and the barrier waits no later than
 * the finite absolute deadline_ms. On success the returned mutation lease
 * retains maintenance EX, admission EX, and lifetime EX until release. On
 * timeout, callback refusal/error, or lock failure it grants no mutation
 * authority and releases every safely releasable guard. UINT64_MAX is
 * rejected because mutation draining must always be bounded. A non-NULL
 * cleanup-only lease_out after IO must still be released by the caller. */
engine_version_cohort_status_t engine_version_cohort_reserve_for_mutation(
    engine_version_cohort_manager_t *manager, uint64_t deadline_ms,
    engine_version_cohort_quiesce_fn quiesce, void *quiesce_context,
    engine_version_cohort_quiesce_result_t *quiesce_result_out,
    engine_version_cohort_lease_t **lease_out);

/* Cheap, non-blocking observation of the crash-released maintenance intent.
 * Participants use the same native gate before admission, so REQUESTED is an
 * authoritative fail-fast signal rather than a filesystem-presence guess. */
engine_version_cohort_maintenance_presence_t engine_version_cohort_maintenance_presence(
    engine_version_cohort_manager_t *manager);

/* Terminal-observer variant for threads whose only safe response to an
 * observation error is immediate process exit. Unlike the general observer,
 * this never logs, flushes stdio, or fail-stops internally when native lock
 * cleanup cannot be completed. It returns MAINTENANCE_IO instead; callers must
 * then terminate immediately without touching borrowed manager state. A
 * REQUESTED result owns no observer lock and may first use a bounded
 * cooperative-cancellation grace period. */
engine_version_cohort_maintenance_presence_t engine_version_cohort_maintenance_presence_terminal(
    engine_version_cohort_manager_t *manager);

/* The daemon holds this separate EX marker for its generation after taking
 * the stable daemon lifetime reservation. A local CLI can therefore
 * distinguish a current coordinated daemon from a pre-cohort daemon without
 * opening an IPC connection or registering a daemon session. A non-NULL
 * claim_out accompanying IO is cleanup-only authority and must be released. */
engine_version_cohort_status_t engine_version_cohort_daemon_claim_acquire(
    engine_version_cohort_manager_t *manager, engine_version_cohort_daemon_claim_t **claim_out);
engine_private_file_lock_status_t engine_version_cohort_daemon_claim_release(
    engine_version_cohort_daemon_claim_t **claim_io);

/* Non-owning marker observation for startup turnover. COORDINATED means a
 * current daemon still holds its generation claim, including the cleanup
 * interval after its listener/lifetime reservation has closed. ABSENT means
 * the marker was acquired and released safely; UNSAFE/IO fail closed. */
engine_version_cohort_daemon_presence_t engine_version_cohort_daemon_claim_presence(
    engine_version_cohort_manager_t *manager);

/* Native marker ownership, never file existence, establishes a coordinated
 * daemon. A retained marker remains authoritative during final cleanup even
 * after listener/lifetime teardown. */
engine_version_cohort_daemon_presence_t engine_version_cohort_daemon_presence(
    engine_version_cohort_manager_t *manager, const engine_daemon_ipc_endpoint_t *endpoint);

/* Standalone CLI presence check under its successfully sealed and retained
 * startup transition. An absent daemon lifetime is authoritative because no
 * current or legacy daemon can start through that guard; an active lifetime
 * must still own the current-generation daemon marker to be coordinated. */
engine_version_cohort_daemon_presence_t engine_version_cohort_daemon_presence_under_transition(
    engine_version_cohort_manager_t *manager, const engine_daemon_ipc_endpoint_t *endpoint,
    const engine_daemon_ipc_local_transition_t *transition);

engine_private_file_lock_status_t engine_version_cohort_lease_release(
    engine_version_cohort_lease_t **lease_io);

/* Refuses teardown while a lease or retryable cleanup handle remains. */
engine_private_file_lock_status_t engine_version_cohort_manager_free(
    engine_version_cohort_manager_t **manager_io);

/* Best-effort persistent conflict record in the same owner-only daemon log
 * used by HELLO conflicts. Admission remains safely rejected if logging fails. */
bool engine_version_cohort_log_conflict(const engine_daemon_conflict_t *conflict);

/* Persist the fail-closed migration case where the stable daemon reservation
 * is active but no current-generation coordination marker can be verified. */
bool engine_version_cohort_log_uncoordinated_daemon(const engine_daemon_build_identity_t *requested);

#endif /* ENGINE_DAEMON_VERSION_COHORT_H */
