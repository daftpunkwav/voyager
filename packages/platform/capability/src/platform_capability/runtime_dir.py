"""Per-user private data directories for standalone entry points.

The domain MCP servers (packages/*/src/*/mcp_server.py) default their data
directories to a fixed name under the system temp dir. That path is
predictable, and on a multi-user Unix host the temp dir is shared, so
another local account could pre-create the directory (or swap it for a
symlink) and capture or corrupt whatever the server writes there.

secure_data_dir() closes that gap at startup: it creates the directory
owner-only, tightens an existing directory it owns, and refuses to start
when the path is not a plain directory or belongs to another user. On
Windows there is no ownership check (the user profile ACL is the isolation
boundary, the same documented limitation as LocalTokenIssuer's 0o600 secret
file).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from tempfile import gettempdir

__all__ = ["secure_data_dir"]


def secure_data_dir(name: str) -> Path:
    """Resolve ``<tempdir>/<name>`` into a safe per-user data directory.

    - missing: create it owner-only (0o700);
    - existing plain directory owned by the current user: keep it, tightening
      group/world permissions to 0o700 (legacy installs may have created it
      through a loose umask);
    - anything else (a file, a symlink, a directory owned by someone else):
      refuse with RuntimeError so the operator sees the tampering instead of
      the server silently writing into a hostile directory.

    A create/create race with another process surfaces as FileExistsError:
    failing the startup is the safe direction (never write into a directory
    this process did not establish).
    """
    path = Path(gettempdir()) / name
    try:
        st = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)  # mkdir() applies the process umask; force 0o700
        return path
    if not stat.S_ISDIR(st.st_mode):
        # A file or a symlink (lstat never follows): refuse rather than
        # write through the attacker-planted entry.
        raise RuntimeError(f"data dir {path} is not a plain directory; refusing to start")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise RuntimeError(f"data dir {path} is owned by another user; refusing to start")
    if os.name != "nt" and st.st_mode & 0o077:
        os.chmod(path, 0o700)
    return path
