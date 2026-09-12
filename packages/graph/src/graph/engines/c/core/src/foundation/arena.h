/*
 * arena.h — Bump allocator with block-based growth.
 *
 * All memory is freed at once via engine_arena_destroy(). Individual frees are
 * not supported — this is by design for per-file extraction where all data
 * has the same lifetime.
 *
 * Restructured from internal/engine/arena.h for the pure C rewrite.
 * New additions: engine_arena_reset() for reuse without realloc.
 */
#ifndef ENGINE_ARENA_H
#define ENGINE_ARENA_H

#include <stddef.h>
#include <stdarg.h>

#define ENGINE_ARENA_MAX_BLOCKS 256
#define ENGINE_ARENA_DEFAULT_BLOCK_SIZE ((size_t)64 * 1024) /* 64KB */

typedef struct {
    char *blocks[ENGINE_ARENA_MAX_BLOCKS];
    size_t block_sizes[ENGINE_ARENA_MAX_BLOCKS]; /* per-block sizes (for stats) */
    int nblocks;
    size_t block_size;  /* current block capacity */
    size_t used;        /* bytes used in current block */
    size_t total_alloc; /* cumulative bytes allocated (for stats) */
} EngineArena;

/* Initialize arena with default block size. */
void engine_arena_init(EngineArena *a);

/* Initialize arena with a custom initial block size. */
void engine_arena_init_sized(EngineArena *a, size_t block_size);

/* Allocate n bytes (8-byte aligned). Returns NULL on OOM. */
void *engine_arena_alloc(EngineArena *a, size_t n);

/* Allocate n bytes, zero-initialized. */
void *engine_arena_calloc(EngineArena *a, size_t n);

/* Duplicate a NUL-terminated string. */
char *engine_arena_strdup(EngineArena *a, const char *s);

/* Duplicate a string of known length, NUL-terminate. */
char *engine_arena_strndup(EngineArena *a, const char *s, size_t len);

/* sprintf into arena memory. */
char *engine_arena_sprintf(EngineArena *a, const char *fmt, ...) __attribute__((format(printf, 2, 3)));

/* Reset arena for reuse: keeps first block, frees the rest. */
void engine_arena_reset(EngineArena *a);

/* Free all blocks. Arena is zeroed after this. */
void engine_arena_destroy(EngineArena *a);

/* Return total bytes allocated (for diagnostics). */
size_t engine_arena_total(const EngineArena *a);

#endif /* ENGINE_ARENA_H */
