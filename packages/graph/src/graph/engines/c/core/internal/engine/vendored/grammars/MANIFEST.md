# Vendored tree-sitter Grammar Manifest

**Provenance + version record for the tree-sitter grammars under this directory.**

The grammars were originally vendored as bare `parser.c`+`scanner.c` with **no recorded upstream version or commit**. This manifest reconstructs that provenance and pins each vendored grammar to a specific upstream commit, cross-verified against two independent registries (nvim-treesitter `parsers.lua` + Helix `languages.toml`).

## How generated
`private/grammar_audit/{discover,resolve_stragglers}.sh` (upstream + tag) → `verify_sources.py` (cross-verify vs nvim-treesitter + Helix, capture pinned commit) → `gen_manifest.py`. Captured 2026-06-02.

## Summary

- Grammars: **50** — Voyager trim (2026-08-28): cut to the 50 most mainstream languages;
  upstream had pruned to 100 on 2026-08-12 (39 low-usage niche grammars; prior round removed 20)
- ABI distribution: **7×** ABI-13 **85×** ABI-14 **64×** ABI-15 (runtime ceiling is ABI 15; never vendor ABI 16 without a runtime upgrade)
- Vendored copies missing LICENSE: **0** — all upstream LICENSE files restored 2026-06-11 (first-party grammars carry the project MIT license; `move` uses the Helix-listed upstream tzakian/tree-sitter-move MIT text, `zsh` uses georgeharker/tree-sitter-zsh MIT)
- `verdict`: VERIFIED-BOTH = our source matches *both* registries; VERIFIED-NVIM/HELIX = matches one; registry-disagreement = registries name a different repo (listed separately); `vendor-maintained` = the language vendor's own grammar, not in nvim/Helix.
- **objectscript_udl / objectscript_routine** (added 2026-06-24): vendored from [intersystems/tree-sitter-objectscript](https://github.com/intersystems/tree-sitter-objectscript) @ `a7ffcdf` — MIT, the InterSystems-official grammars (a niche vendor language, hence `vendor-maintained`, not in nvim-treesitter/Helix). **Re-vendor note:** each `scanner.c`'s upstream `#include "../../common/scanner.h"` is repointed to a per-directory `objectscript_common.h` (a verbatim copy of upstream `common/scanner.h`), because this repo's shared `vendored/common/scanner.h` belongs to the cfml/fsharp grammars and differs. The generated `parser.c`/`scanner.c` are otherwise byte-for-byte upstream — on re-vendor, re-apply only that single include rename. **Local modification (2026-07-16):** in `objectscript_common.h`, two loop counters `uint8_t i` were widened to `int i` (the `reverse_marker` scan and the `html_marker_buffer` reversal) to clear CodeQL `cpp/comparison-with-wider-type` — a false positive in practice (both lengths are hard-bounded by `MARKER_BUFFER_MAX_LEN = 30`, so `uint8_t` could never wrap), fixed for cleanliness. On re-vendor, re-apply this widening too (or upstream it at intersystems/tree-sitter-objectscript).
- **mojo** (added 2026-07-01): vendored from [lsh/tree-sitter-mojo](https://github.com/lsh/tree-sitter-mojo) @ `33193a99afe6` — MIT, ABI 15. Helix tracks `lsh/tree-sitter-mojo` as its Mojo grammar source, but the Helix-pinned commit (`3d7c53b8038f`) no longer resolves in the upstream repository after a force-push, so this vendor uses current upstream `main` rather than the stale registry SHA. Security review covered only the vendored C surface (`parser.c`, `scanner.c`, `tree_sitter/*.h`) plus upstream license/provenance metadata; no package manager hooks, workflow files, prompt/agent instruction files, or generated lockfiles were vendored.

> ⚠️ **Pinned commit = the revision nvim-treesitter/Helix vendor** (battle-tested, canonical source), not bleeding-edge HEAD. When re-vendoring, update the pinned commit here.

## Custom extraction handling (definition extraction)

The grammars below carry **custom definition-extraction support** in
`internal/engine/extract_defs.c` (and `internal/engine/lang_specs.c`). Their function /
definition nodes do **not** expose a `name` field that the generic extractor reads
— the name lives on a nested/child/parent node, or (for the Lisp family) a
definition is a macro form inside a generic `list` node with no dedicated def
node. Without this handling these grammars produce only a file-level `Module`
node and **zero functions/types**. A future grammar refresh that changes these
node shapes must update the corresponding branch.

Guarded by the `contract_all_grammars_in_graph` graph-breadth test in
`tests/test_lang_contract.c` (each was reproduced as a failing case before the fix).

| grammar | custom handling |
|---|---|
| clojure  | `extract_lisp_def`: `(defn …)` / `(def …)` head-symbol forms in `list_lit` |
| haskell  | `func_types` += `bind` (nullary value bindings; `signature` suppressed) |

## Local source patches (applied atop pinned upstream)

The grammars below carry a small local patch to their vendored `scanner.c`, on
top of the pinned upstream commit recorded in the vendoring table below.
Re-vendoring from upstream must re-apply these.

| grammar | location | patch | reason |
|---|---|---|---|

## Vendored from verified upstream

| grammar | cur ABI | upstream repo | pinned commit | verdict | LICENSE |
|---|:---:|---|---|---|:---:|
| bash | 15 | tree-sitter/tree-sitter-bash | `a06c2e4415e9` | VERIFIED-BOTH | ✅ |
| c | 15 | tree-sitter/tree-sitter-c | `ae19b676b13b` | VERIFIED-BOTH | ✅ |
| c_sharp | 15 | tree-sitter/tree-sitter-c-sharp | `88366631d598` | VERIFIED-BOTH | ✅ |
| clojure | 14 | sogaiu/tree-sitter-clojure | `e43eff80d17c` | VERIFIED-BOTH | ✅ |
| cmake | 14 | uyha/tree-sitter-cmake | `c7b2a71e7f8e` | VERIFIED-BOTH | ✅ |
| cpp | 14 | tree-sitter/tree-sitter-cpp | `8b5b49eb196b` | VERIFIED-BOTH | ✅ |
| css | 15 | tree-sitter/tree-sitter-css | `dda5cfc5722c` | VERIFIED-BOTH | ✅ |
| dart | 15 | UserNobody14/tree-sitter-dart | `0fc19c3a57b1` | VERIFIED-BOTH | ✅ |
| dockerfile | 14 | camdencheek/tree-sitter-dockerfile | `971acdd90856` | VERIFIED-BOTH | ✅ |
| elixir | 14 | elixir-lang/tree-sitter-elixir | `7937d3b4d65f` | VERIFIED-BOTH | ✅ |
| erlang | 14 | WhatsApp/tree-sitter-erlang | `1d78195c4fbb` | VERIFIED-NVIM | ✅ |
| go | 15 | tree-sitter/tree-sitter-go | `2346a3ab1bb3` | VERIFIED-BOTH | ✅ |
| graphql | 13 | bkegley/tree-sitter-graphql | `5e66e961eee4` | VERIFIED-BOTH | ✅ |
| groovy | 15 | murtaza64/tree-sitter-groovy | `781d9cd1b482` | VERIFIED-BOTH | ✅ |
| haskell | 15 | tree-sitter/tree-sitter-haskell | `7fa19f195803` | VERIFIED-HELIX | ✅ |
| hcl | 15 | tree-sitter-grammars/tree-sitter-hcl | `64ad62785d44` | MISMATCH | ✅ |
| html | 14 | tree-sitter/tree-sitter-html | `73a3947324f6` | VERIFIED-BOTH | ✅ |
| ini | 15 | justinmk/tree-sitter-ini | `e4018b517613` | VERIFIED-BOTH | ✅ |
| java | 14 | tree-sitter/tree-sitter-java | `e10607b45ff7` | VERIFIED-BOTH | ✅ |
| javascript | 15 | tree-sitter/tree-sitter-javascript | `58404d8cf191` | VERIFIED-BOTH | ✅ |
| json | 14 | tree-sitter/tree-sitter-json | `001c28d7a298` | VERIFIED-BOTH | ✅ |
| julia | 15 | tree-sitter/tree-sitter-julia | `8454f2667172` | VERIFIED-HELIX | ✅ |
| kotlin | 14 | fwcd/tree-sitter-kotlin | `93bfeee1555d` | VERIFIED-BOTH | ✅ |
| lua | 15 | tree-sitter-grammars/tree-sitter-lua | `10fe0054734e` | VERIFIED-BOTH | ✅ |
| make | 15 | tree-sitter-grammars/tree-sitter-make | `70613f3d812c` | VERIFIED-NVIM | ✅ |
| markdown | 15 | tree-sitter-grammars/tree-sitter-markdown | `f969cd3ae3f9` | VERIFIED-BOTH | ✅ |
| matlab | 15 | acristoffers/tree-sitter-matlab | `c2390a59016f` | VERIFIED-BOTH | ✅ |
| objc | 14 | tree-sitter-grammars/tree-sitter-objc | `181a81b8f23a` | VERIFIED-NVIM | ✅ |
| perl | 14 | tree-sitter-perl/tree-sitter-perl | `ea9667dc65a8` | VERIFIED-BOTH | ✅ |
| php | 15 | tree-sitter/tree-sitter-php | `3f2465c217d0` | VERIFIED-BOTH | ✅ |
| powershell | 15 | airbus-cert/tree-sitter-powershell | `73800ecc8bdd` | VERIFIED-BOTH | ✅ |
| python | 15 | tree-sitter/tree-sitter-python | `v0.25.0` | VERIFIED-BOTH | ✅ |
| r | 14 | r-lib/tree-sitter-r | `0e6ef7741712` | VERIFIED-BOTH | ✅ |
| ruby | 14 | tree-sitter/tree-sitter-ruby | `ad907a69da0c` | VERIFIED-BOTH | ✅ |
| rust | 15 | tree-sitter/tree-sitter-rust | `77a3747266f4` | VERIFIED-BOTH | ✅ |
| scala | 15 | tree-sitter/tree-sitter-scala | `14c5cfd2b8e0` | VERIFIED-BOTH | ✅ |
| scss | 14 | serenadeai/tree-sitter-scss | `c478c6868648` | MISMATCH | ✅ |
| sql | 15 | DerekStride/tree-sitter-sql | `851e9cb257ba` | VERIFIED-BOTH | ✅ |
| svelte | 14 | tree-sitter-grammars/tree-sitter-svelte | `ae5199db4775` | VERIFIED-NVIM | ✅ |
| swift | 14 | alex-pinkus/tree-sitter-swift | `8abb3e8b3325` | VERIFIED-BOTH | ✅ |
| toml | 14 | tree-sitter-grammars/tree-sitter-toml | `64b56832c2cf` | MISMATCH | ✅ |
| tsx | 14 | tree-sitter/tree-sitter-typescript | `75b3874edb2d` | VERIFIED-BOTH | ✅ |
| typescript | 14 | tree-sitter/tree-sitter-typescript | `75b3874edb2d` | VERIFIED-BOTH | ✅ |
| vue | 15 | tree-sitter-grammars/tree-sitter-vue | `ce8011a414fd` | VERIFIED-NVIM | ✅ |
| xml | 14 | tree-sitter-grammars/tree-sitter-xml | `5000ae8f22d1` | VERIFIED-NVIM | ✅ |
| yaml | 14 | tree-sitter-grammars/tree-sitter-yaml | `4463985dfccc` | VERIFIED-NVIM | ✅ |
| zig | 14 | tree-sitter-grammars/tree-sitter-zig | `6479aa13f32f` | VERIFIED-BOTH | ✅ |

## First-party / self-maintained

These grammars are not tracked by nvim-treesitter or Helix and are **not**
swept from any upstream. Treat them as owned source; do not overwrite from a
public repo. **Corrected during the byte-identity license audit 2026-06-12:**
the original "authored in-house" classification was too coarse — six of the
twelve are self-maintained **forks** whose vendored LICENSE names the original
upstream author (correctly retained). The table now records the true origin.

### Authored in-house (project MIT, (c) DeusData)

| grammar | cur ABI | LICENSE |
|---|:---:|:---:|
| protobuf | 13 | ✅ project MIT |

### Self-maintained forks (upstream license retained, byte-verified 2026-06-12)

| grammar | cur ABI | original upstream | license |
|---|:---:|---|---|
| assembly | 14 | RubixDev/tree-sitter-assembly (**repo deleted from GitHub** — our retained MIT copy, (c) 2023 RubixDev, is the surviving grant) | MIT |

## Registry disagreement — RESOLVED (license audit 2026-06-12)

Our resolved repo differs from what the registries list, and the two registries disagree with each other (or only one lists it). **Maintainer decision recorded 2026-06-12** during the license re-audit: each grammar is pinned to the canonical source below, its license was verified against that repo via the GitHub API, and the matching LICENSE file is vendored in the grammar directory. When re-vendoring, use the canonical source column.

| grammar | canonical source (decided) | license (verified) | nvim-treesitter | Helix |
|---|---|---|---|---|

Notes: the previously-resolved `tree-sitter-grammars/tree-sitter-move` and
`tree-sitter-grammars/tree-sitter-zsh` repos no longer exist on GitHub (404),
so `move` and `zsh` pin to the surviving registry-listed upstreams.

## License re-audit conclusion (2026-06-12)

Every grammar directory carries a LICENSE/COPYING file; every non-first-party
grammar has a verified upstream with a permissive license (MIT except:
clojure CC0-1.0, jinja2 + just Apache-2.0). First-party grammars carry the
project MIT license. **Removal rule applied: the `nim` grammar
(alaviss/tree-sitter-nim, MPL-2.0) was removed 2026-06-12 — MPL-2.0 is
outside the permissive-only vendoring policy; it was also the largest
vendored grammar (66 MB). All remaining grammars are permissive.**
The CI ScanCode license gate enforces this state going forward.
