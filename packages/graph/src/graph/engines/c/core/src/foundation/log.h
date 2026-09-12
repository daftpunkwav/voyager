/*
 * log.h — Structured key-value logging to stderr.
 *
 * Design:
 *   - All output goes to stderr (stdout is reserved for MCP JSON-RPC)
 *   - Structured text format: "level=info msg=pass.timing pass=defs elapsed_ms=42"
 *   - Optional JSON format for local structured parsing
 *   - Levels: DEBUG, INFO, WARN, ERROR
 *   - Level filtering at runtime via engine_log_set_level() or the
 *     ENGINE_LOG_LEVEL env var (see engine_log_init_from_env)
 *   - Thread-safe (each fprintf is atomic on POSIX for lines < PIPE_BUF)
 */
#ifndef ENGINE_LOG_H
#define ENGINE_LOG_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef enum {
    ENGINE_LOG_DEBUG = 0,
    ENGINE_LOG_INFO = 1,
    ENGINE_LOG_WARN = 2,
    ENGINE_LOG_ERROR = 3,
    ENGINE_LOG_NONE = 4 /* disable all logging */
} EngineLogLevel;

typedef enum {
    ENGINE_LOG_FORMAT_TEXT = 0,
    ENGINE_LOG_FORMAT_JSON = 1,
} EngineLogFormat;

typedef enum {
    ENGINE_LOG_SINK_REPLACE = 0,
    ENGINE_LOG_SINK_TEE = 1,
} EngineLogSinkMode;

/* Apply the ENGINE_LOG_LEVEL environment variable to the runtime log level.
 * Accepts (case-insensitive) "debug", "info", "warn", "error", "none", or
 * the numeric equivalents 0..4 matching EngineLogLevel. Unknown, empty, or
 * unset values leave the level unchanged (fail-open).
 *
 * Also applies ENGINE_LOG_FORMAT=text|json. If unset, the current format is left
 * unchanged. Call once at startup before any threads or log lines. */
void engine_log_init_from_env(void);

/* Set minimum log level (default: INFO). */
void engine_log_set_level(EngineLogLevel level);

/* Get current log level. */
EngineLogLevel engine_log_get_level(void);

/* Set/get output format. Default is text. */
void engine_log_set_format(EngineLogFormat format);
EngineLogFormat engine_log_get_format(void);

/* Core logging function. msg is a short semantic tag.
 * Variadic args are key-value pairs: (const char *key, const char *value)...
 * Terminated by NULL key.
 *
 * Example:
 *   engine_log(ENGINE_LOG_INFO, "pass.timing",
 *           "pass", "defs", "elapsed_ms", "42", NULL);
 *
 * Output:
 *   level=info msg=pass.timing pass=defs elapsed_ms=42
 */
void engine_log(EngineLogLevel level, const char *msg, ...);

/* Convenience macros. */
#define engine_log_debug(msg, ...) engine_log(ENGINE_LOG_DEBUG, msg, ##__VA_ARGS__, NULL)
#define engine_log_info(msg, ...) engine_log(ENGINE_LOG_INFO, msg, ##__VA_ARGS__, NULL)

/* Always-delivered internal control/discovery record. It bypasses the level
 * threshold and always uses the JSON encoding, so exact values (paths with
 * spaces or control bytes) survive unambiguously; it flows through the
 * configured sink like every other record. Reserve it for the rare
 * discovery/control events that ordinary log filtering must never suppress
 * (e.g. diagnostics.start path announcement). */
void engine_log_control_record(const char *msg, ...);
#define engine_log_control(msg, ...) engine_log_control_record(msg, ##__VA_ARGS__, NULL)
#define engine_log_warn(msg, ...) engine_log(ENGINE_LOG_WARN, msg, ##__VA_ARGS__, NULL)
#define engine_log_error(msg, ...) engine_log(ENGINE_LOG_ERROR, msg, ##__VA_ARGS__, NULL)

/* Log with integer value (avoids sprintf for common case). */
void engine_log_int(EngineLogLevel level, const char *msg, const char *key, int64_t value);

/* Operational event helpers. They deliberately avoid request bodies, headers,
 * arguments, and query strings. */
void engine_log_mcp_request(const char *method, const char *tool_name, bool is_error,
                         int64_t duration_us);
void engine_log_http_request(const char *component, const char *method, const char *path, int status,
                          int64_t duration_ms, size_t request_bytes, size_t response_bytes);

/* Optional log sink callback — called with the formatted log line. */
typedef void (*engine_log_sink_fn)(const char *line);
void engine_log_set_sink(engine_log_sink_fn fn);
void engine_log_set_sink_ex(engine_log_sink_fn fn, EngineLogSinkMode mode);

#endif /* ENGINE_LOG_H */
