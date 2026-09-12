/*
 * str_intern.h — String interning pool.
 *
 * Deduplicates strings: identical strings share a single allocation.
 * Returns stable pointers — safe to compare by pointer equality after interning.
 *
 * Uses an arena for string storage (bulk free) + hash table for dedup lookup.
 */
#ifndef ENGINE_STR_INTERN_H
#define ENGINE_STR_INTERN_H

#include <stddef.h>
#include <stdint.h>

typedef struct EngineInternPool EngineInternPool;

/* Create a new intern pool. */
EngineInternPool *engine_intern_create(void);

/* Free the pool and all interned strings. */
void engine_intern_free(EngineInternPool *pool);

/* Intern a NUL-terminated string. Returns a stable pointer.
 * The same input always returns the same pointer. */
const char *engine_intern(EngineInternPool *pool, const char *s);

/* Intern a string of known length. */
const char *engine_intern_n(EngineInternPool *pool, const char *s, size_t len);

/* Number of unique strings in the pool. */
uint32_t engine_intern_count(const EngineInternPool *pool);

/* Total bytes stored (unique strings only). */
size_t engine_intern_bytes(const EngineInternPool *pool);

#endif /* ENGINE_STR_INTERN_H */
