# scripts/ — Build and test entry points

> **Voyager entry:** to build this repo's MCP indexing engine, use [`build.ps1`](build.ps1) (`make -f Makefile graph-engine`).
> Makefile: the build entry point is `Makefile`.
>
> Upstream ops scripts — installer / release packaging / stress tests / security audits / CI venue gates / git hooks, etc. —
> were removed when migrating into Voyager (Voyager only uses the build and basic test chain;
> see the repo's git history if needed).

## Retained scripts

| Script                                                                                        | Purpose                                                                                          |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `build.sh` / `build.ps1`                                                                      | Production build (artifact `graph-engine`)                                                       |
| `clean.sh` / `env.sh` / `path-safety.sh`                                                      | Cleanup, build environment, path-safety preflight                                                |
| `test.sh` / `test-windows.ps1` / `run-tests-parallel.sh`                                      | Test chain                                                                                       |
| `check-no-test-skips.sh` / `check-nolint-whitelist.sh`(+`.txt`) / `lint-mem-gate.py`(+`.txt`) | Static policy checks                                                                             |
| `lint.sh`                                                                                     | clang-tidy + cppcheck + clang-format                                                             |
| `msan.sh`                                                                                     | MemorySanitizer test lane                                                                        |
| `smoke-test.sh`                                                                               | Upstream functional smoke (the memory wiring notes for `src/foundation/mem.c` are anchored here) |
| `ci/check-binary-composition.sh`                                                              | Binary composition check referenced by test.sh                                                   |
| `gen-integrations-hash.sh`                                                                    | Regenerates the hash of `assets/engine-integrations.json`                                        |
| `gen-py-stdlib.py`                                                                            | Regenerates Python LSP standard-library type data (see THIRD_PARTY.md)                           |
| `extract_nomic_vectors.py`                                                                    | Regenerates nomic embedding vectors (see THIRD_PARTY.md)                                         |
| `vendored-checksums.txt` / `security-allowlist.txt`                                           | Vendored integrity records / URL allowlist records                                               |

Every entry point supports `--help`; unknown arguments raise a usage error.
