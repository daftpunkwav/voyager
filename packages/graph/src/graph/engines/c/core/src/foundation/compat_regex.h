/*
 * compat_regex.h — Portable regular expression API.
 *
 * POSIX: direct wrappers around <regex.h> (regcomp, regexec, regfree).
 * Windows: TODO — vendor TRE regex or use a C++ wrapper around <regex>.
 *
 * Uses our own types so callers never include <regex.h> directly.
 */
#ifndef ENGINE_COMPAT_REGEX_H
#define ENGINE_COMPAT_REGEX_H

#include "foundation/constants.h"
#include <stddef.h>

/* ── Flags ────────────────────────────────────────────────────── */

#define ENGINE_REG_EXTENDED 1
#define ENGINE_REG_ICASE 2
#define ENGINE_REG_NOSUB 4
#define ENGINE_REG_NEWLINE 8

/* ── Error codes ──────────────────────────────────────────────── */

#define ENGINE_REG_OK 0
#define ENGINE_REG_NOMATCH (-1)

/* ── Types ────────────────────────────────────────────────────── */

/* Opaque regex handle — sized to hold the platform's regex_t. */
typedef struct {
    /* ENGINE_SZ_256 bytes should be large enough for any platform's regex_t.
     * POSIX regex_t is typically 48-ENGINE_SZ_64 bytes; TRE is ~80 bytes. */
    char opaque[ENGINE_SZ_256];
} engine_regex_t;

typedef struct {
    int rm_so; /* byte offset of match start, -1 if no match */
    int rm_eo; /* byte offset past match end */
} engine_regmatch_t;

/* ── Functions ────────────────────────────────────────────────── */

/* Compile a regular expression. Returns ENGINE_REG_OK on success, non-zero on error. */
int engine_regcomp(engine_regex_t *r, const char *pattern, int flags);

/* Execute compiled regex against str. nmatch/matches may be 0/NULL.
 * eflags: 0 or combination of platform-specific exec flags.
 * Returns ENGINE_REG_OK on match, ENGINE_REG_NOMATCH on no match. */
int engine_regexec(const engine_regex_t *r, const char *str, int nmatch, engine_regmatch_t *matches,
                int eflags);

/* Free compiled regex. */
void engine_regfree(engine_regex_t *r);

#endif /* ENGINE_COMPAT_REGEX_H */
