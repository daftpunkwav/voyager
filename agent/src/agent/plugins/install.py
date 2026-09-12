"""Plugin install primitives: safe zip extraction, directory-source
validation, and placement on disk.

Pure file-movement primitives only; discovery/approval semantics live in
manager. Declarative only: no plugin script is ever executed and there is
no post-install hook.

Key rules:
- Zip root convention: plugin.json at the zip root means the root is the
  plugin root; otherwise exactly one top-level directory containing
  plugin.json qualifies (packaging junk such as __MACOSX and top-level
  dot-dirs is ignored); zero or multiple candidates are rejected, never
  guessed.
- Limits: zip <= 20 MiB (same cap for directory sources), <= 500 files,
  <= 5 MiB per file; exceeding any limit is INVALID_INPUT and rejects the
  whole plugin. Zip bombs are contained by the file-count x per-file caps.
- Zip slip: member names must not contain ``..`` segments, absolute paths,
  drive letters, backslashes, or NUL, and each resolved target must stay
  inside the extraction root; violations abort the whole plugin.
  Extraction happens only in the system temp dir, so plugins/ receives
  nothing until every check passes. Windows junctions are not detected by
  is_symlink (content only ever flows into plugins/, noted here for
  transparency).
- Symlinks: zip members are written as plain files (Python zipfile creates
  no links); any symlink (file or dir) inside a directory source is
  rejected, preventing copies of out-of-root content into plugins/.
- Placement: copytree into plugins/<name>/; on failure the caller cleans up
  the partial directory. The temp extraction area uses the system temp dir
  and is removed after install; no copy is left in runtime data.
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from platform_contracts import ErrorSuffix, ServiceError

#: Zip size / directory-source total cap (tunable; tests pin behavior via monkeypatch)
MAX_ZIP_BYTES = 20 * 1024 * 1024
#: Per-file cap after extraction / copy
MAX_FILE_BYTES = 5 * 1024 * 1024
#: File count cap
MAX_FILES = 500

#: Plugin names are used directly as path segments: safe directory-name
#: characters only plus Windows reserved names rejected (the `_` prefix is
#: allowed, matching discover semantics; see safe_plugin_name)
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_NAME_MAX_LEN = 64
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _invalid(message: str) -> ServiceError:
    return ServiceError("agent", ErrorSuffix.INVALID_INPUT, message)


def safe_plugin_name(name: str) -> str:
    """Validate manifest.name as a usable target directory name: non-empty,
    <= 64 chars, safe characters, not a reserved name.

    The `_` prefix is allowed (consistent with discover); invalid names
    reject the install, never guess a directory name.
    """
    text = name.strip()
    if (
        not text
        or len(text) > _NAME_MAX_LEN
        or not _NAME_RE.match(text)
        or text.upper() in _WINDOWS_RESERVED
    ):
        raise _invalid(
            f"plugin name is not usable as an install directory name (<=64 chars, letters/digits/_/.-): {name!r}"
        )
    return text


def _member_dest(root: Path, arcname: str) -> Path | None:
    """Zip member name -> absolute extraction target; None when unsafe
    (zip slip)."""
    if not arcname or "\\" in arcname or "\x00" in arcname:
        return None
    pure = PurePosixPath(arcname)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        return None
    if len(arcname) > 1 and arcname[1] == ":":  # Windows drive letter (C:/...)
        return None
    target = (root / arcname).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _locate_plugin_root(extract_root: Path) -> Path:
    """Zip root convention: the root itself is the plugin root, or exactly one
    top-level directory contains plugin.json."""
    if (extract_root / "plugin.json").is_file():
        return extract_root
    top_dirs = [
        p
        for p in extract_root.iterdir()
        if p.is_dir() and p.name != "__MACOSX" and not p.name.startswith(".")
    ]
    if len(top_dirs) == 1 and (top_dirs[0] / "plugin.json").is_file():
        return top_dirs[0]
    raise _invalid(
        "no unique plugin.json found in the zip (convention: the zip root is the"
        " plugin root, or exactly one top-level directory contains plugin.json)"
    )


def extract_plugin_zip(zip_path: Path, tmp: Path) -> Path:
    """Extract the zip into tmp (system temp area), validating path safety and
    limits per member; returns the plugin root.

    Any violation rejects the whole plugin; the plugins/ directory is not
    touched at all here (extract and validate first, place later).
    """
    try:
        size = zip_path.stat().st_size
    except OSError as exc:
        raise _invalid(f"cannot read the zip file: {exc}") from exc
    if size > MAX_ZIP_BYTES:
        raise _invalid(f"zip exceeds the {MAX_ZIP_BYTES // (1024 * 1024)} MiB limit")
    extract_root = tmp / "unpacked"
    extract_root.mkdir(parents=True, exist_ok=True)  # even an empty zip needs a locatable root
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _invalid(f"not a valid zip file: {exc}") from exc
    with archive:
        members = [i for i in archive.infolist() if not i.is_dir()]
        if len(members) > MAX_FILES:
            raise _invalid(f"zip contains more than {MAX_FILES} files")
        for info in members:
            target = _member_dest(extract_root, info.filename)
            if target is None:
                raise _invalid(
                    f"zip contains unsafe path entries (e.g. ../ or absolute paths); whole plugin rejected: "
                    f"{info.filename!r}"
                )
            try:
                with archive.open(info) as f:
                    data = f.read(MAX_FILE_BYTES + 1)
            except RuntimeError as exc:  # encrypted zips surface as RuntimeError
                raise _invalid(
                    "zip is encrypted; installing encrypted zips is not supported"
                ) from exc
            if len(data) > MAX_FILE_BYTES:
                raise _invalid(
                    f"single file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MiB limit: "
                    f"{info.filename!r}"
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:  # path too deep / disk full etc.: readable message, not INTERNAL
                raise _invalid(f"failed to write extracted entry {info.filename!r}: {exc}") from exc
    return _locate_plugin_root(extract_root)


def prepare_source_dir(src: Path) -> Path:
    """Validate a directory install source: really exists, no symlinks, within
    limits; returns the source path."""
    if not src.is_dir():
        raise _invalid(f"plugin source directory does not exist or is not a directory: {src}")
    files: list[Path] = []
    for base, dirs, names in os.walk(src, followlinks=False):
        here = Path(base)
        for d in dirs:
            if (here / d).is_symlink():
                raise ServiceError(
                    "agent",
                    ErrorSuffix.FORBIDDEN,
                    f"source directory contains a symlink; refusing to install: {d}",
                )
        for n in names:
            fp = here / n
            if fp.is_symlink():
                raise ServiceError(
                    "agent",
                    ErrorSuffix.FORBIDDEN,
                    f"source directory contains a symlink; refusing to install: {n}",
                )
            files.append(fp)
    if len(files) > MAX_FILES:
        raise _invalid(f"source directory contains more than {MAX_FILES} files")
    total = 0
    for fp in files:
        size = fp.stat().st_size
        if size > MAX_FILE_BYTES:
            raise _invalid(
                f"single file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MiB limit: "
                f"{fp.relative_to(src)}"
            )
        total += size
    if total > MAX_ZIP_BYTES:
        raise _invalid(
            f"source directory exceeds the {MAX_ZIP_BYTES // (1024 * 1024)} MiB total size limit"
        )
    return src


def place_plugin(src: Path, dest: Path) -> None:
    """Copy a validated plugin root into plugins/<name>/ (copy, not move;
    dest must not exist)."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
