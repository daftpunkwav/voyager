/*
 * compat_thread.h — Portable threading: pthreads on POSIX, Win32 threads on Windows.
 *
 * Provides: thread create/join, mutex, aligned allocation.
 * All have zero overhead on POSIX (thin inlines or macros).
 */
#ifndef ENGINE_COMPAT_THREAD_H
#define ENGINE_COMPAT_THREAD_H

#include <stddef.h>

/* ── Thread ───────────────────────────────────────────────────── */

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

typedef struct {
    HANDLE handle;
} engine_thread_t;

#else /* POSIX */

#include <pthread.h>

typedef struct {
    pthread_t handle;
} engine_thread_t;

#endif

/* Create a thread with the given stack size (0 = OS default).
 * fn receives arg. Returns 0 on success. */
int engine_thread_create(engine_thread_t *t, size_t stack_size, void *(*fn)(void *), void *arg);

/* Wait for thread to finish. Returns 0 on success. */
int engine_thread_join(engine_thread_t *t);

/* Detach thread so resources are freed on exit. Returns 0 on success. */
int engine_thread_detach(engine_thread_t *t);

/* ── Mutex ────────────────────────────────────────────────────── */

#ifdef _WIN32

typedef struct {
    CRITICAL_SECTION cs;
} engine_mutex_t;

#else

typedef struct {
    pthread_mutex_t mtx;
} engine_mutex_t;

#endif

void engine_mutex_init(engine_mutex_t *m);
void engine_mutex_lock(engine_mutex_t *m);
void engine_mutex_unlock(engine_mutex_t *m);
void engine_mutex_destroy(engine_mutex_t *m);

/* ── Aligned allocation ───────────────────────────────────────── */

/* Allocate size bytes aligned to alignment boundary.
 * Returns 0 on success, non-zero on failure. *ptr receives the allocation. */
int engine_aligned_alloc(void **ptr, size_t alignment, size_t size);

/* Free memory from engine_aligned_alloc. */
void engine_aligned_free(void *ptr);

#endif /* ENGINE_COMPAT_THREAD_H */
