#ifndef ENGINE_SECURE_RANDOM_H
#define ENGINE_SECURE_RANDOM_H

#include <stdbool.h>
#include <stddef.h>

/* Fill a caller-owned buffer from the operating system CSPRNG. This is a
 * direct platform API/file operation and never invokes a shell or subprocess. */
bool engine_secure_random(void *buffer, size_t length);

/* Overwrite sensitive caller-owned storage through volatile writes so the
 * compiler cannot discard the erasure as an unobservable dead store. */
void engine_secure_zero(void *buffer, size_t length);

#endif /* ENGINE_SECURE_RANDOM_H */
