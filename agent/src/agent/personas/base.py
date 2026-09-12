"""Persona presets: pure data. Persona and style are orthogonal; capability
templates trim the tool surface at dispatch time.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    display_name: str
    style: str  # style (warm / sardonic / rigorous ...)
    system_prompt: str
    default_mode: str = "react"
    tool_allow: tuple[str, ...] | None = None  # capability template; None = no trimming
