"""Skill system: resident index + on-demand full text (loader);
repeated-flow organization (organizer).
"""

from agent.skills.loader import SkillLoader
from agent.skills.organizer import SkillOrganizer

__all__ = ["SkillLoader", "SkillOrganizer"]
