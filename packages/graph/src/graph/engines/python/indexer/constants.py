"""Extension sets, skipped directories, and indexing-mode limits
(mirrors the native engine's discover).
"""

from __future__ import annotations

# These directories can never be un-skipped by .engineignore negation rules committed to the repo
SAFETY_CORE_DIRS = frozenset({".git", "node_modules", ".worktrees", ".claude-worktrees"})

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    "vendor",
    "target",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "Pods",
    ".idea",
    ".vscode",
    "__snapshots__",
}

CODE_EXT = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".scala",
    ".vue",
    ".svelte",
}
DOC_EXT = {".md", ".mdx", ".markdown", ".rst"}
CONFIG_EXT = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sql",
    ".graphql",
    ".gql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".xml",
    ".tf",
    ".proto",
}
ALL_EXT = CODE_EXT | DOC_EXT | CONFIG_EXT

MODE_LIMITS = {
    # fast: few files, but still include md Sections (otherwise node counts drop severely)
    "fast": {"max_files": 800, "max_bytes": 400_000, "layout_iters": 0},
    "moderate": {"max_files": 8_000, "max_bytes": 1_500_000, "layout_iters": 0},
    # full: same order of magnitude as the native engine; no force-directed layout server-side
    "full": {"max_files": 100_000, "max_bytes": 5_000_000, "layout_iters": 0},
    "cross-repo-intelligence": {"max_files": 0, "max_bytes": 0, "layout_iters": 0},
}
