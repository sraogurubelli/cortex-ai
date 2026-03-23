"""
Agent Skills System

Discovers SKILL.md files from a configurable directory, parses metadata,
builds a virtual filesystem for agent context, and provides middleware
to inject skill instructions.

Ported from ml-infra unified_chat/agents/unified/skills/ without
deepagents dependency — uses a lightweight built-in implementation.
"""

from .discovery import SkillDefinition, discover_skills
from .loader import build_skill_files
from .middleware import SkillsMiddleware

__all__ = [
    "SkillDefinition",
    "discover_skills",
    "build_skill_files",
    "SkillsMiddleware",
]
