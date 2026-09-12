/*
 * progress_sink.h — Human-readable progress for one-shot CLI commands.
 *
 * Installs a log sink that maps structured pipeline events to phase labels.
 * Interactive terminals enable it automatically; --progress forces it when
 * stderr is redirected.
 * Usage:
 *   engine_progress_sink_init(stderr);
 *   // ... run pipeline ...
 *   engine_progress_sink_fini();
 */
#ifndef ENGINE_PROGRESS_SINK_H
#define ENGINE_PROGRESS_SINK_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

/* Interactive terminals get lifecycle feedback automatically. --progress
 * forces the same behavior for redirected stderr without touching stdout. */
bool engine_cli_progress_enabled(bool explicitly_requested, bool stderr_is_tty);
void engine_cli_progress_start(FILE *out, const char *tool_name);
void engine_cli_progress_finish(FILE *out, const char *tool_name, bool success, uint64_t elapsed_ms);

void engine_progress_sink_init(FILE *out);
void engine_progress_sink_fini(void);
void engine_progress_sink_fn(const char *line);

#endif
