"""Console output decoding shared by run_shell and run_snippet: try UTF-8
first, then the Windows console codepage (GBK/cp936 on zh-CN systems - forcing
UTF-8 there turns every CJK byte into replacement characters, the mojibake
seen in traces)."""

from __future__ import annotations

import locale
import os


def decode_console_output(raw: bytes) -> str:
    """Decode child-process output; falls back to lossy replacement so a
    undecodable byte stream never raises into the tool result."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    candidates: tuple[str, ...]
    if os.name == "nt":
        candidates = ("gbk", "utf-16")
    else:
        # A GBK/cp936 byte stream is not limited to Windows hosts (SSH to a
        # legacy Windows box, cross-platform CI artifacts), so keep the same
        # fallbacks after the locale's preferred encoding.
        preferred = locale.getpreferredencoding()
        candidates = (preferred, "gbk", "utf-16") if preferred else ("gbk", "utf-16")
    if b"\x00" in raw:
        # Console-codepage text never contains NUL bytes; NULs signal UTF-16
        # output (some PowerShell pipelines). GBK would "succeed" on those
        # NUL-interleaved bytes and return mojibake, so UTF-16 is tried first.
        candidates = ("utf-16", *candidates)
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


__all__ = ["decode_console_output"]
