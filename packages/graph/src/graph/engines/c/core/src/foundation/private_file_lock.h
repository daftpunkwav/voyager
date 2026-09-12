/*
 * private_file_lock.h — Secure locks inside a prevalidated private directory.
 *
 * This is an internal foundation primitive. It deliberately does not choose a
 * product runtime path; callers must supply an opaque directory handle created
 * by the platform runtime-path layer.
 */
#ifndef ENGINE_PRIVATE_FILE_LOCK_H
#define ENGINE_PRIVATE_FILE_LOCK_H

#include <stdint.h>

typedef enum {
    ENGINE_PRIVATE_FILE_LOCK_OK = 0,
    ENGINE_PRIVATE_FILE_LOCK_BUSY = 1,
    ENGINE_PRIVATE_FILE_LOCK_UNSAFE = 2,
    ENGINE_PRIVATE_FILE_LOCK_IO = 3,
} engine_private_file_lock_status_t;

typedef enum {
    ENGINE_PRIVATE_FILE_LOCK_SH = 1,
    ENGINE_PRIVATE_FILE_LOCK_EX = 2,
} engine_private_file_lock_mode_t;

typedef struct engine_private_lock_directory engine_private_lock_directory_t;
typedef struct engine_private_file_lock engine_private_file_lock_t;

/* Basenames are fixed internal names, never paths. Acquisition is
 * nonblocking; BUSY is the only contention result. Stable lock files are never
 * unlinked by this API. Any non-NULL *lock_out on any status owns native
 * cleanup state and must be passed to engine_private_file_lock_release(). */
engine_private_file_lock_status_t engine_private_file_lock_try_acquire(
    engine_private_lock_directory_t *directory, const char *base_name,
    engine_private_file_lock_mode_t mode, engine_private_file_lock_t **lock_out);

/* OK terminally closes the native handle and clears *lock_io. IO retains a
 * non-NULL object only while native ownership is safely retryable. POSIX
 * close(2) consumes descriptor ownership once invoked even if it reports an
 * error, so that terminal IO case clears *lock_io to prevent fd-reuse races. */
engine_private_file_lock_status_t engine_private_file_lock_release(engine_private_file_lock_t **lock_io);

void engine_private_lock_directory_close(engine_private_lock_directory_t *directory);
const char *engine_private_lock_directory_path(const engine_private_lock_directory_t *directory);

#endif /* ENGINE_PRIVATE_FILE_LOCK_H */
