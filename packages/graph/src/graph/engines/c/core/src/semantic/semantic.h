/*
 * semantic.h — Algorithmic code embeddings for SEMANTICALLY_RELATED edges.
 *
 * Combines 11 signals into a unified similarity score without external
 * models or dependencies.  All signals derived from graph buffer metadata
 * and the existing AST walk.
 *
 * Signals:
 *   1. TF-IDF on metadata tokens (vocabulary overlap)
 *   2. Random Indexing with co-occurrence (within-codebase synonym bridging)
 *   3. MinHash structural (existing, decoded from "fp" property)
 *   4. API Signature vectors (same callees → related)
 *   5. Type Signature vectors (same param/return types → related)
 *   6. Module Proximity (same directory → boost)
 *   7. Decorator Pattern vectors (same annotations → related)
 *   8. AST Structural Profile (control flow shape, expression types)
 *   9. Approximate Data Flow (params→return, params→condition)
 *  10. Graph Diffusion (transitive closure via neighbor blending)
 *  11. Halstead-Lite (operator/operand complexity profile)
 *
 * Note: signals 8, 9, 11 are computed at extraction time (ast_profile.h)
 * and stored in properties_json.  The rest are computed in the post-pass.
 */
#ifndef ENGINE_SEMANTIC_H
#define ENGINE_SEMANTIC_H

#include <stdbool.h>
#include <stdint.h>

#include "semantic/rotsq.h"

/* ── Configuration ───────────────────────────────────────────────── */

/* Random Indexing dimension. 256 is sufficient for <500K functions. */
/* 768 = nomic-embed-code embedding dimension.  Matches PRETRAINED_DIM. */
enum { ENGINE_SEM_DIM = 768 };

/* Random Indexing: non-zero entries per sparse random vector. */
enum { ENGINE_SEM_SPARSE_NNZE = 8 };

/* Co-occurrence window half-width. */
enum { ENGINE_SEM_WINDOW = 5 };

/* Frequent-token subsampling cap for co-occurrence enrichment. Code token
 * frequencies are Zipfian — a handful of tokens (int, static, return, …) occur
 * in 10^4–10^5 functions and dominate the O(occurrences × window × dim) corpus
 * finalize cost. When a token has more than this many occurrences, we stride-
 * sample down to ~this count: the enriched vector is L2-normalized afterward, so
 * an evenly-spaced subsample preserves its *direction* while bounding the work.
 * Rare/high-IDF (discriminative) tokens fall under the cap and are untouched.
 * Mirrors word2vec/GloVe frequent-word subsampling. */
enum { ENGINE_SEM_MAX_OCCUR = 512 };

/* Default score threshold for SEMANTICALLY_RELATED edge emission.
 * 0.75 balances recall with precision: validated ~95% precision on
 * Linux kernel (0.80 = 100% but only 90 edges, 0.70 = 2047 edges
 * but ~80% precision). */
#define ENGINE_SEM_EDGE_THRESHOLD 0.75

/* Maximum SEMANTICALLY_RELATED edges per node. */
enum { ENGINE_SEM_MAX_EDGES = 10 };

/* AST structural profile: 25 float features per function (control flow,
 * nesting, expression types, literals, data flow, Halstead). */
enum { ENGINE_SEM_AST_PROFILE_DIMS = 25 };

/* MinHash fingerprint length (must match simhash/minhash.h ENGINE_MINHASH_K). */
enum { ENGINE_SEM_MINHASH_K = 64 };

/* Signal weights (sum to ~1.0, proximity is a multiplier). */
typedef struct {
    float w_tfidf;
    float w_ri;
    float w_minhash;
    float w_api;
    float w_type;
    float w_decorator;
    float w_struct_profile;
    float w_dataflow;
    float threshold;
    int max_edges;
} engine_sem_config_t;

/* Get default config (can be overridden via env vars). */
engine_sem_config_t engine_sem_get_config(void);

/* Check if semantic embeddings are enabled (ENGINE_SEMANTIC_ENABLED=1). */
bool engine_sem_is_enabled(void);

/* ── Token extraction ────────────────────────────────────────────── */

/* Maximum tokens per function from metadata (name + qn + path + sig + docstring + params). */
enum { ENGINE_SEM_MAX_TOKENS = 512 };

/* Split a name into tokens: camelCase, snake_case, dot.separated.
 * Writes up to max_out tokens into out. Returns token count.
 * Tokens are lowercased. Caller must free each token. */
int engine_sem_tokenize(const char *name, char **out, int max_out);

/* ── Dense vectors ───────────────────────────────────────────────── */

/* A fixed-size dense vector for cosine similarity. */
typedef struct {
    float v[ENGINE_SEM_DIM];
} engine_sem_vec_t;

/* Compute cosine similarity between two dense vectors. */
float engine_sem_cosine(const engine_sem_vec_t *a, const engine_sem_vec_t *b);

/* Generate a deterministic sparse random vector for a token.
 * Uses xxHash(token) as seed. Output has SEM_SPARSE_NNZE non-zeros. */
void engine_sem_random_index(const char *token, engine_sem_vec_t *out);

/* Eagerly initialize the pretrained token lookup map.
 * Call this BEFORE dispatching parallel work that invokes engine_sem_random_index,
 * so the lazy init races are avoided entirely on the hot path. */
void engine_sem_ensure_ready(void);

/* Normalize a vector to unit length in-place. */
void engine_sem_normalize(engine_sem_vec_t *v);

/* Add src to dst: dst[i] += scale * src[i]. */
void engine_sem_vec_add_scaled(engine_sem_vec_t *dst, const engine_sem_vec_t *src, float scale);

/* ── Per-function semantic data ──────────────────────────────────── */

/* All computed signals for one function. */
typedef struct {
    int64_t node_id;
    const char *file_path;
    const char *file_ext;

    /* Sparse TF-IDF: stored as parallel arrays of (token_index, weight). */
    int *tfidf_indices;
    float *tfidf_weights;
    int tfidf_len;

    /* Dense vectors for RI, API, Type, Decorator. */
    /* Quantized semantic vectors (rotated 4-bit scalar quantization — see
     * rotsq.h). The dense 768-float versions exist only transiently in the
     * build workers: 4 x 3 KB resident floats per function were ~9.4 GB on
     * the linux kernel; the codes are ~0.5 KB each. Scoring uses the exact
     * code-expansion inner-product estimator (deterministic). */
    engine_rsq_code_t ri_code;
    engine_rsq_code_t api_code;
    engine_rsq_code_t type_code;
    engine_rsq_code_t deco_code;

    /* AST profile as float vector (decoded from "sp" property). */
    float struct_profile[ENGINE_SEM_AST_PROFILE_DIMS];

    /* MinHash fingerprint (decoded from "fp" property). */
    bool has_minhash;
    uint32_t minhash[ENGINE_SEM_MINHASH_K];
} engine_sem_func_t;

/* ── Corpus-level data ───────────────────────────────────────────── */

/* Opaque corpus handle for IDF and Random Indexing state. */
typedef struct engine_sem_corpus engine_sem_corpus_t;

/* Create a new corpus from function data. */
engine_sem_corpus_t *engine_sem_corpus_new(void);

/* Register a function's tokens in the corpus (for IDF counting). */
void engine_sem_corpus_add_doc(engine_sem_corpus_t *corpus, const char **tokens, int count);

/* Batch-build the corpus from pre-tokenized documents (PARALLEL variant).
 * `all_tokens` layout: all_tokens[f * max_tokens_per_doc + t] = token pointer.
 * `token_counts[f]` = number of tokens in document f.
 * This replaces a loop of engine_sem_corpus_add_doc() calls. */
void engine_sem_corpus_add_docs_batch(engine_sem_corpus_t *corpus, char **all_tokens,
                                   const int *token_counts, int doc_count, int max_tokens_per_doc);

/* Finalize: compute IDF, build enriched token vectors via co-occurrence. */
void engine_sem_corpus_finalize(engine_sem_corpus_t *corpus);

/* Get IDF weight for a token. Returns 0.0 for unknown tokens. */
float engine_sem_corpus_idf(const engine_sem_corpus_t *corpus, const char *token);

/* Get the enriched Random Indexing vector for a token (after co-occurrence). */
const engine_sem_vec_t *engine_sem_corpus_ri_vec(const engine_sem_corpus_t *corpus, const char *token);

/* Get the total document count. */
int engine_sem_corpus_doc_count(const engine_sem_corpus_t *corpus);

/* Get the total token count (vocabulary size). */
int engine_sem_corpus_token_count(const engine_sem_corpus_t *corpus);

/* Get token name and enriched vector by index (for serialization).
 * Returns NULL if index is out of range. */
const char *engine_sem_corpus_token_at(const engine_sem_corpus_t *corpus, int index,
                                    const engine_sem_vec_t **out_vec, float *out_idf);

/* Free corpus. */
void engine_sem_corpus_free(engine_sem_corpus_t *corpus);

/* ── Combined scoring ────────────────────────────────────────────── */

/* Compute combined similarity score between two functions. */
float engine_sem_combined_score(const engine_sem_func_t *a, const engine_sem_func_t *b,
                             const engine_sem_config_t *cfg);

/* Module proximity multiplier based on file paths. */
float engine_sem_proximity(const char *path_a, const char *path_b);

/* ── Graph diffusion ─────────────────────────────────────────────── */

/* Apply one iteration of graph diffusion to a combined embedding.
 * Blends with mean of top-k neighbor embeddings (α=0.3). */
void engine_sem_diffuse(engine_sem_vec_t *combined, const engine_sem_vec_t *neighbors, int neighbor_count,
                     float alpha);

#endif /* ENGINE_SEMANTIC_H */
