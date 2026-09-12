#ifndef ENGINE_AC_H
#define ENGINE_AC_H

#include <stdint.h>

// Forward declaration — full struct in ac.c
typedef struct EngineAutomaton EngineAutomaton;

// Input for batch LZ4 scanning.
typedef struct {
    const char *data;
    int compressed_len;
    int original_len;
} EngineLz4Entry;

// Output for batch LZ4 scanning.
typedef struct {
    int file_index;
    uint64_t bitmask;
} EngineLz4Match;

// Output for batch name scanning.
typedef struct {
    int name_index;
    int pattern_id;
} EngineMatchResult;

// Build an Aho-Corasick automaton from patterns.
EngineAutomaton *engine_ac_build(const char **patterns, const int *lengths, int count,
                           const uint8_t *alpha_map, int alpha_size);
void engine_ac_free(EngineAutomaton *ac);

// Single-text scanning (returns bitmask of matched pattern IDs).
uint64_t engine_ac_scan_bitmask(const EngineAutomaton *ac, const char *text, int text_len);

// LZ4-compressed scanning.
uint64_t engine_ac_scan_lz4_bitmask(const EngineAutomaton *ac, const char *compressed, int compressed_len,
                                 int original_len);
int engine_ac_scan_lz4_batch(const EngineAutomaton *ac, const EngineLz4Entry *entries, int num_entries,
                          EngineLz4Match *out_matches, int max_matches);

// Batch name scanning.
int engine_ac_scan_batch(const EngineAutomaton *ac, const char *names_buf, const int *name_offsets,
                      const int *name_lengths, int num_names, EngineMatchResult *out_matches,
                      int max_matches);

// Introspection.
int engine_ac_num_states(const EngineAutomaton *ac);
int engine_ac_num_patterns(const EngineAutomaton *ac);
int engine_ac_table_bytes(const EngineAutomaton *ac);

#endif // ENGINE_AC_H
